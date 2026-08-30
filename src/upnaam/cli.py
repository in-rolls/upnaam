"""Command-line interface for the generic Upnaam pipeline."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from upnaam.adapters.punjab import (
    build_punjab_elector_artifact,
    write_punjab_audit,
    write_punjab_summary,
)
from upnaam.canonicalization import (
    EvidenceTier,
    VariantEvidence,
    apply_canonical_map,
    canonical_map_from_frame,
    cluster_variants,
    generate_variant_candidates,
)
from upnaam.normalization import NORMALIZATION_REVISION, normalize_name
from upnaam.policy import load_resolver_policy
from upnaam.resolver import resolve_electors
from upnaam.schema import CANONICALIZATION_REVISION
from upnaam.selection import extract_surname_candidates
from upnaam.tables import read_table, write_table

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from upnaam.selection import SurnameCandidateResult


def _require_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise ValueError(f"input table is missing column: {column}")
    result = frame[column]
    if isinstance(result, pd.DataFrame):
        raise ValueError(f"input table contains duplicate column: {column}")
    return result


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


def _candidate_frequencies(args: argparse.Namespace) -> dict[str, int]:
    frame = read_table(args.input)
    tokens = _require_column(frame, args.token_column)
    if args.count_column:
        counts = cast(
            "pd.Series",
            pd.to_numeric(_require_column(frame, args.count_column), errors="raise"),
        )
        if tokens.isna().any():
            raise ValueError("frequency tokens must be nonnull")
        if (counts <= 0).any() or counts.isna().any():
            raise ValueError("frequency counts must be positive and nonnull")
        frequencies = pd.DataFrame(
            {"token": tokens.astype(str), "count": counts.astype(int)}
        )
        grouped = frequencies.groupby("token", sort=True)["count"].sum()
        return {str(token): int(count) for token, count in grouped.items()}
    tokens = tokens.dropna().astype(str)
    return {str(token): int(count) for token, count in tokens.value_counts().items()}


def _canonicalize_candidates(args: argparse.Namespace) -> None:
    candidates = generate_variant_candidates(
        _candidate_frequencies(args),
        max_distance=args.max_distance,
        min_similarity=args.min_similarity,
    )
    columns = (
        "left",
        "right",
        "distance",
        "similarity",
        "left_frequency",
        "right_frequency",
    )
    write_table(
        pd.DataFrame((asdict(item) for item in candidates), columns=columns),
        args.output,
    )


def _canonicalize_build(args: argparse.Namespace) -> None:
    frame = read_table(args.input)
    required = {"left", "right", "support", "similarity", "source"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"evidence table is missing columns: {sorted(missing)}")
    evidence = []
    for row in frame.to_dict(orient="records"):
        tier_value = row.get("evidence_tier", EvidenceTier.LINKED_RECORD.value)
        preferred = row.get("preferred")
        preferred_missing = preferred is None or cast("bool", pd.isna(preferred))
        accepted_value = row.get("accepted", True)
        if isinstance(accepted_value, str):
            if accepted_value.casefold() not in {"true", "false"}:
                raise ValueError("accepted evidence values must be true or false")
            accepted = accepted_value.casefold() == "true"
        else:
            if cast("bool", pd.isna(accepted_value)):
                raise ValueError("accepted evidence values must be nonnull")
            accepted = bool(accepted_value)
        evidence.append(
            VariantEvidence(
                left=str(row["left"]),
                right=str(row["right"]),
                support=int(row["support"]),
                similarity=float(row["similarity"]),
                source=str(row["source"]),
                evidence_tier=EvidenceTier(tier_value),
                accepted=accepted,
                preferred=None if preferred_missing else str(preferred),
            )
        )
    mappings = cluster_variants(
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
        for item in mappings
    ]
    columns = (
        "variant",
        "canonical",
        "cluster_size",
        "direct_support",
        "sources",
        "evidence_tiers",
    )
    write_table(pd.DataFrame(rows, columns=columns), args.output)


def _canonicalize_apply(args: argparse.Namespace) -> None:
    records = read_table(args.input)
    mapping = canonical_map_from_frame(read_table(args.mapping))
    output = apply_canonical_map(
        records,
        mapping,
        normalized_column=args.normalized_column,
        revision=args.revision,
        provenance=args.provenance,
    )
    write_table(output, args.output)


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

    canonicalize = commands.add_parser("canonicalize", help="canonicalize spellings")
    canonical_commands = canonicalize.add_subparsers(dest="operation", required=True)
    candidates = _table_command(
        canonical_commands,
        "candidates",
        "generate string-similarity candidates",
        _canonicalize_candidates,
    )
    candidates.add_argument("--token-column", default="surname_latin_normalized")
    candidates.add_argument("--count-column")
    candidates.add_argument("--max-distance", type=int, default=2)
    candidates.add_argument("--min-similarity", type=float, default=0.75)

    build = _table_command(
        canonical_commands,
        "build",
        "build a map from accepted evidence",
        _canonicalize_build,
    )
    build.add_argument("--min-support", type=int, default=2)
    build.add_argument("--min-similarity", type=float, default=0.75)

    apply = _table_command(
        canonical_commands, "apply", "apply an accepted map", _canonicalize_apply
    )
    apply.add_argument("mapping", type=_path)
    apply.add_argument("--normalized-column", default="surname_latin_normalized")
    apply.add_argument("--revision", default=CANONICALIZATION_REVISION)
    apply.add_argument("--provenance", default="accepted_variant_map")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run an Upnaam command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = cast("Callable[[argparse.Namespace], None]", args.handler)
    handler(args)


if __name__ == "__main__":
    main()
