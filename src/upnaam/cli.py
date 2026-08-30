"""Command-line interface for the generic Upnaam pipeline."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from upnaam.adapters.bihar import (
    BIHAR_LINKAGE_BASIS,
    BIHAR_REFERENCE_REVISION,
    build_bihar_land_reference_labels,
    write_bihar_reference_audit,
    write_bihar_reference_summary,
)
from upnaam.adapters.punjab import (
    build_punjab_elector_artifact,
    write_punjab_audit,
    write_punjab_summary,
)
from upnaam.adapters.rajasthan import (
    build_rajasthan_surname_evidence,
    write_rajasthan_evidence_audit,
)
from upnaam.artifacts import write_manifest
from upnaam.canonicalization import (
    AnchorEvidence,
    RankedAnchorCandidate,
    apply_reconciliation,
    decide_anchor_candidates,
    rank_anchor_candidates,
    reconciliation_index_from_frame,
)
from upnaam.normalization import NORMALIZATION_REVISION, normalize_name
from upnaam.policy import load_resolver_policy
from upnaam.resolver import resolve_electors
from upnaam.selection import extract_surname_candidates
from upnaam.tables import read_table, write_table

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Mapping, Sequence

    from upnaam.selection import SurnameCandidateResult


def _require_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise ValueError(f"input table is missing column: {column}")
    result = frame[column]
    if isinstance(result, pd.DataFrame):
        raise ValueError(f"input table contains duplicate column: {column}")
    return result


def _required_string(row: Mapping[Hashable, Any], column: str) -> str:
    value = row[column]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{column} must contain nonempty strings")
    return value


def _normalize(args: argparse.Namespace) -> None:
    frame = read_table(args.input)
    values = _require_column(frame, args.name_column)
    output = frame.copy()
    output[args.output_column] = values.map(normalize_name).astype("string")
    output["normalization_revision"] = NORMALIZATION_REVISION
    write_table(output, args.output)


def _select(args: argparse.Namespace) -> None:
    frame = read_table(args.input)
    values = _require_column(frame, args.name_column)
    selected = cast(
        "pd.Series",
        values.map(
            lambda value: extract_surname_candidates(
                value, min_letters=args.min_letters
            )
        ),
    )
    output = frame.copy()
    for position in ("first", "last"):
        output[f"surname_{position}_raw"] = selected.map(
            lambda result, position=position: (
                getattr(result, f"{position}_candidate").raw
                if getattr(result, f"{position}_candidate") is not None
                else None
            )
        ).astype("string")
        output[f"surname_{position}_normalized"] = selected.map(
            lambda result, position=position: (
                getattr(result, f"{position}_candidate").normalized
                if getattr(result, f"{position}_candidate") is not None
                else None
            )
        ).astype("string")
    output["candidate_abstained"] = selected.map(
        lambda result: cast("SurnameCandidateResult", result).abstained
    )
    output["candidate_abstention_reason"] = selected.map(
        lambda result: cast("SurnameCandidateResult", result).abstention_reason
    ).astype("string")
    write_table(output, args.output)


def _resolve(args: argparse.Namespace) -> None:
    frame = read_table(args.input)
    policy = load_resolver_policy(args.policy) if args.policy else None
    write_table(resolve_electors(frame, policy=policy), args.output)


def _resolve_punjab(args: argparse.Namespace) -> None:
    report = build_punjab_elector_artifact(
        args.roll,
        args.transliteration,
        args.output,
        batch_size=args.batch_size,
    )
    if args.audit:
        write_punjab_audit(args.audit, report)
    if args.summary:
        write_punjab_summary(args.summary, report)


def _bihar_reference_labels(args: argparse.Namespace) -> None:
    report = build_bihar_land_reference_labels(
        args.input, args.output, batch_size=args.batch_size
    )
    if args.audit:
        write_bihar_reference_audit(args.audit, report)
    if args.summary:
        write_bihar_reference_summary(args.summary, report)
    if args.manifest:
        outputs = [args.output]
        outputs.extend(path for path in (args.audit, args.summary) if path is not None)
        write_manifest(
            args.manifest,
            stage="bihar_land_reference_labels",
            inputs=[args.input],
            outputs=outputs,
            row_counts={
                "source_links": report.source_links,
                "accepted_labels": report.accepted_labels,
                "abstained_labels": report.abstained_labels,
                "excluded_conflicts": report.excluded_conflicts,
            },
            parameters={
                "linkage_basis": BIHAR_LINKAGE_BASIS,
                "normalization_revision": NORMALIZATION_REVISION,
                "reference_revision": BIHAR_REFERENCE_REVISION,
                "surname_rule": "last_eligible_token",
            },
        )


def _reconcile_rank(args: argparse.Namespace) -> None:
    frame = read_table(args.input)
    required = {
        "observed_form",
        "context",
        "canonical_id",
        "canonical_label",
        "support",
        "similarity",
        "source",
        "evidence_tier",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"anchor evidence is missing columns: {sorted(missing)}")
    evidence = [
        AnchorEvidence(
            observed_form=_required_string(row, "observed_form"),
            context=_required_string(row, "context"),
            canonical_id=_required_string(row, "canonical_id"),
            canonical_label=_required_string(row, "canonical_label"),
            support=int(row["support"]),
            similarity=float(row["similarity"]),
            source=_required_string(row, "source"),
            evidence_tier=_required_string(row, "evidence_tier"),
        )
        for row in frame.to_dict(orient="records")
    ]
    candidates = rank_anchor_candidates(
        evidence,
        min_support=args.min_support,
        min_similarity=args.min_similarity,
    )
    rows = [
        {
            **asdict(item),
            "sources": "|".join(item.sources),
            "evidence_tiers": "|".join(item.evidence_tiers),
        }
        for item in candidates
    ]
    columns = [
        "observed_form",
        "context",
        "canonical_id",
        "canonical_label",
        "rank",
        "eligible",
        "support",
        "total_support",
        "support_share",
        "weighted_similarity",
        "sources",
        "evidence_tiers",
        "min_support_threshold",
        "min_similarity_threshold",
        "reconciliation_revision",
    ]
    write_table(pd.DataFrame(rows, columns=pd.Index(columns)), args.output)


def _parse_bool(value: object) -> bool:
    if value is True or value is False:
        return bool(value)
    if isinstance(value, str) and value.casefold() in {"true", "false"}:
        return value.casefold() == "true"
    raise ValueError("boolean columns must contain only true or false")


def _split_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item for item in value.split("|") if item)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    if value is None or cast("bool", pd.isna(cast("Any", value))):
        return ()
    raise ValueError("multi-value candidate fields have an invalid value")


def _reconcile_decide(args: argparse.Namespace) -> None:
    frame = read_table(args.input)
    required = {
        "observed_form",
        "context",
        "canonical_id",
        "canonical_label",
        "rank",
        "eligible",
        "support",
        "total_support",
        "support_share",
        "weighted_similarity",
        "sources",
        "evidence_tiers",
        "min_support_threshold",
        "min_similarity_threshold",
        "reconciliation_revision",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"ranked candidates are missing columns: {sorted(missing)}")
    candidates = [
        RankedAnchorCandidate(
            observed_form=_required_string(row, "observed_form"),
            context=_required_string(row, "context"),
            canonical_id=_required_string(row, "canonical_id"),
            canonical_label=_required_string(row, "canonical_label"),
            rank=int(row["rank"]),
            eligible=_parse_bool(row["eligible"]),
            support=int(row["support"]),
            total_support=int(row["total_support"]),
            support_share=float(row["support_share"]),
            weighted_similarity=float(row["weighted_similarity"]),
            sources=_split_values(row["sources"]),
            evidence_tiers=_split_values(row["evidence_tiers"]),
            min_support_threshold=int(row["min_support_threshold"]),
            min_similarity_threshold=float(row["min_similarity_threshold"]),
            reconciliation_revision=_required_string(row, "reconciliation_revision"),
        )
        for row in frame.to_dict(orient="records")
    ]
    decisions = decide_anchor_candidates(candidates)
    rows = [{**asdict(item), "status": item.status.value} for item in decisions]
    columns = [
        "observed_form",
        "context",
        "canonical_id",
        "canonical_label",
        "status",
        "reason",
        "candidate_count",
        "eligible_candidate_count",
        "top_support",
        "runner_up_support",
        "min_support_threshold",
        "min_similarity_threshold",
        "reconciliation_revision",
    ]
    write_table(pd.DataFrame(rows, columns=pd.Index(columns)), args.output)
    if args.audit:
        statuses = Counter(item.status.value for item in decisions)
        accepted = [item for item in decisions if item.status.value == "accepted"]
        thresholds = {
            (item.min_support_threshold, item.min_similarity_threshold)
            for item in decisions
        }
        report = {
            "observed_forms": len(decisions),
            "candidate_rows": len(candidates),
            "accepted": statuses["accepted"],
            "accepted_identity": sum(
                item.observed_form == item.canonical_label for item in accepted
            ),
            "accepted_variant": sum(
                item.observed_form != item.canonical_label for item in accepted
            ),
            "ambiguous": statuses["ambiguous"],
            "unresolved": statuses["unresolved"],
            "min_support_threshold": (
                next(iter(thresholds))[0] if thresholds else None
            ),
            "min_similarity_threshold": (
                next(iter(thresholds))[1] if thresholds else None
            ),
        }
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.audit.with_suffix(f"{args.audit.suffix}.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
        temporary.replace(args.audit)


def _reconcile_apply(args: argparse.Namespace) -> None:
    records = read_table(args.input)
    decisions = reconciliation_index_from_frame(read_table(args.decisions))
    output = apply_reconciliation(
        records,
        decisions,
        normalized_column=args.normalized_column,
        context=args.context,
        context_column=args.context_column,
        provenance=args.provenance,
    )
    write_table(output, args.output)


def _rajasthan_evidence(args: argparse.Namespace) -> None:
    report = build_rajasthan_surname_evidence(
        args.input, args.output, batch_size=args.batch_size
    )
    if args.audit:
        write_rajasthan_evidence_audit(args.audit, report)


def _path(value: str) -> Path:
    return Path(value)


def _table_command(
    subparsers: Any,
    name: str,
    help_text: str,
    handler: Callable[[argparse.Namespace], None],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name, help=help_text)
    parser.add_argument("input", type=_path)
    parser.add_argument("output", type=_path)
    parser.set_defaults(handler=handler)
    return parser


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(prog="upnaam")
    commands = parser.add_subparsers(dest="command", required=True)

    normalize = _table_command(commands, "normalize", "normalize names", _normalize)
    normalize.add_argument("--name-column", default="name")
    normalize.add_argument("--output-column", default="name_normalized")

    select = _table_command(commands, "select", "emit positional candidates", _select)
    select.add_argument("--name-column", default="name")
    select.add_argument("--min-letters", type=int, default=2)

    resolve = _table_command(commands, "resolve", "resolve electoral names", _resolve)
    resolve.add_argument("--policy", type=_path)

    punjab = commands.add_parser("resolve-punjab", help="build the Punjab artifact")
    punjab.add_argument("roll", type=_path)
    punjab.add_argument("transliteration", type=_path)
    punjab.add_argument("output", type=_path)
    punjab.add_argument("--audit", type=_path)
    punjab.add_argument("--summary", type=_path)
    punjab.add_argument("--batch-size", type=int, default=100_000)
    punjab.set_defaults(handler=_resolve_punjab)

    bihar = commands.add_parser(
        "labels-bihar-land", help="build Bihar land-record reference labels"
    )
    bihar.add_argument("input", type=_path)
    bihar.add_argument("output", type=_path)
    bihar.add_argument("--audit", type=_path)
    bihar.add_argument("--summary", type=_path)
    bihar.add_argument("--manifest", type=_path)
    bihar.add_argument("--batch-size", type=int, default=100_000)
    bihar.set_defaults(handler=_bihar_reference_labels)

    reconcile = commands.add_parser("reconcile", help="reconcile surname spellings")
    reconcile_commands = reconcile.add_subparsers(dest="operation", required=True)
    rank = _table_command(
        reconcile_commands,
        "rank",
        "rank directed anchor evidence",
        _reconcile_rank,
    )
    rank.add_argument("--min-support", type=int, default=2)
    rank.add_argument("--min-similarity", type=float, default=0.75)

    decide = _table_command(
        reconcile_commands,
        "decide",
        "accept one anchor or preserve ambiguity",
        _reconcile_decide,
    )
    decide.add_argument("--audit", type=_path)

    apply = _table_command(
        reconcile_commands,
        "apply",
        "apply reconciliation decisions",
        _reconcile_apply,
    )
    apply.add_argument("decisions", type=_path)
    apply.add_argument("--normalized-column", default="surname_latin_normalized")
    apply.add_argument("--context", default="global")
    apply.add_argument("--context-column")
    apply.add_argument("--provenance", default="anchored_reconciliation")

    rajasthan = commands.add_parser(
        "evidence-rajasthan", help="build Rajasthan surname anchor evidence"
    )
    rajasthan.add_argument("input", type=_path)
    rajasthan.add_argument("output", type=_path)
    rajasthan.add_argument("--audit", type=_path)
    rajasthan.add_argument("--batch-size", type=int, default=100_000)
    rajasthan.set_defaults(handler=_rajasthan_evidence)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run an Upnaam command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = cast("Callable[[argparse.Namespace], None]", args.handler)
    handler(args)


if __name__ == "__main__":
    main()
