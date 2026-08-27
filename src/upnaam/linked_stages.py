"""Alignment, variant, and family-surname stages for accepted links."""

from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from rapidfuzz.distance import Levenshtein

from upnaam.alignment import align_names
from upnaam.candidates import extract_surname_candidates
from upnaam.clustering import VariantEvidence, cluster_variants
from upnaam.edit_model import summarize_edits

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from upnaam.policy import SurnamePosition


def _sex_group(value: object) -> str:
    """Collapse source-specific sex labels for stratified diagnostics."""
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"f", "female"}:
            return "female"
        if normalized in {"m", "male"}:
            return "male"
    return "unknown"


def align_link_table(source: Path, output: Path) -> int:
    """Expand linked name pairs into token alignment operations.

    Args:
        source: Unified accepted-link artifact.
        output: Token-operation Parquet artifact.

    Returns:
        Number of alignment operations written.

    Raises:
        ValueError: If the accepted-link artifact contains no rows.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    parquet = pq.ParquetFile(source)
    writer: pq.ParquetWriter | None = None
    row_count = 0
    try:
        for batch in parquet.iter_batches(batch_size=50_000):
            rows: list[dict[str, object]] = []
            for link in batch.to_pandas().itertuples(index=False):
                operations = align_names(link.roll_name_raw, link.external_name_raw)
                edit_learning_eligible = link.edit_learning_eligible and all(
                    operation.kind in {"exact", "substitute"}
                    for operation in operations
                )
                for operation_index, operation in enumerate(operations):
                    rows.append(
                        {
                            "source": link.source,
                            "link_tier": link.link_tier,
                            "link_id": link.link_id,
                            "operation_index": operation_index,
                            "kind": operation.kind,
                            "roll_token": operation.roll_token,
                            "external_token": operation.external_token,
                            "normalized_distance": operation.normalized_distance,
                            "roll_position": operation.roll_position,
                            "external_position": operation.external_position,
                            "edit_learning_eligible": edit_learning_eligible,
                            "omission_eligible": link.omission_eligible,
                        }
                    )
            table = pa.Table.from_pylist(rows)
            if writer is None:
                writer = pq.ParquetWriter(output, table.schema, compression="zstd")
            writer.write_table(table)
            row_count += table.num_rows
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        raise ValueError("accepted link artifact contains no rows")
    return row_count


def resolve_linked_surnames(source: Path, output: Path) -> int:
    """Resolve recorded surnames for accepted external-record links.

    Args:
        source: Unified accepted-link artifact.
        output: One recorded-surname result per accepted link.

    Returns:
        Number of linked records written.

    Notes:
        The external record may split a single roll token only when its final
        eligible token is an exact suffix of the untouched roll name and a
        nontrivial prefix remains. This is segmentation evidence, not a family
        surname absent from the roll.
    """
    schema = pa.schema(
        [
            ("source", pa.string()),
            ("link_tier", pa.string()),
            ("link_id", pa.string()),
            ("roll_id", pa.string()),
            ("roll_name_raw", pa.string()),
            ("external_name_raw", pa.string()),
            ("sex", pa.string()),
            ("surname", pa.string()),
            ("surname_raw", pa.string()),
            ("surname_position", pa.string()),
            ("surname_provenance", pa.string()),
            ("abstained", pa.bool_()),
            ("abstention_reason", pa.string()),
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(output, schema, compression="zstd")
    row_count = 0
    try:
        parquet = pq.ParquetFile(source)
        for batch in parquet.iter_batches(batch_size=50_000):
            rows: list[dict[str, object]] = []
            for link in batch.to_pandas().itertuples(index=False):
                roll = extract_surname_candidates(link.roll_name_raw)
                external = extract_surname_candidates(link.external_name_raw)
                surname = roll.surname
                provenance = "written_final_token" if surname is not None else None
                reason = roll.abstention_reason
                if (
                    surname is None
                    and reason == "single-token-name"
                    and len(roll.tokens) == 1
                    and external.surname is not None
                    and isinstance(link.roll_name_raw, str)
                    and link.roll_name_raw.endswith(external.surname.raw)
                ):
                    prefix = link.roll_name_raw[: -len(external.surname.raw)]
                    if sum(character.isalpha() for character in prefix) >= 2:
                        surname = external.surname
                        provenance = (
                            "land_record_segmentation"
                            if link.source == "bihar_land"
                            else "ration_card_segmentation"
                        )
                        reason = None
                rows.append(
                    {
                        "source": link.source,
                        "link_tier": link.link_tier,
                        "link_id": link.link_id,
                        "roll_id": link.roll_id,
                        "roll_name_raw": link.roll_name_raw,
                        "external_name_raw": link.external_name_raw,
                        "sex": _sex_group(link.sex),
                        "surname": None if surname is None else surname.normalized,
                        "surname_raw": None if surname is None else surname.raw,
                        "surname_position": None if surname is None else "last",
                        "surname_provenance": provenance,
                        "abstained": surname is None,
                        "abstention_reason": reason,
                    }
                )
            table = pa.Table.from_pylist(rows, schema=schema)
            writer.write_table(table)
            row_count += table.num_rows
    finally:
        writer.close()
    return row_count


def learn_edit_artifact(source: Path, output: Path) -> dict[str, int]:
    """Summarize edits from eligible non-exact linked token pairs.

    Args:
        source: Token alignment artifact.
        output: Destination JSON edit artifact.

    Returns:
        Eligible substitution counts by source.
    """
    frame = pd.read_parquet(source)
    eligible = frame.loc[
        frame["edit_learning_eligible"] & (frame["kind"] == "substitute")
    ].copy()
    payload: dict[str, object] = {
        "interpretation": "Observed counts, not probabilities or calibrated costs",
        "sources": {},
    }
    counts: dict[str, int] = {}
    for source_name, group in eligible.groupby("source", sort=True):
        pairs = list(zip(group["roll_token"], group["external_token"], strict=True))
        payload["sources"][source_name] = summarize_edits(pairs)  # type: ignore[index]
        counts[str(source_name)] = len(group)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return counts


def build_variant_table(
    source: Path,
    output: Path,
    *,
    min_support: int = 2,
    min_similarity: float = 0.75,
) -> int:
    """Build complete-link variant clusters from eligible substitutions.

    Args:
        source: Token alignment artifact.
        output: Variant-to-canonical Parquet artifact.
        min_support: Required accepted links per spelling pair.
        min_similarity: Required normalized Levenshtein similarity.

    Returns:
        Number of variant mappings written.

    Raises:
        ValueError: If a substitution operation lacks string tokens or a
            clustering threshold is invalid.
    """
    frame = pd.read_parquet(source)
    eligible = frame.loc[
        frame["edit_learning_eligible"] & (frame["kind"] == "substitute")
    ].copy()
    evidence: list[VariantEvidence] = []
    grouped = eligible.groupby(["source", "roll_token", "external_token"], dropna=False)
    for (source_name, roll_token, external_token), group in grouped:
        if not isinstance(roll_token, str) or not isinstance(external_token, str):
            raise ValueError("substitution alignments must contain two string tokens")
        similarity = 1 - Levenshtein.normalized_distance(roll_token, external_token)
        evidence.append(
            VariantEvidence(
                left=roll_token,
                right=external_token,
                support=len(group),
                similarity=similarity,
                source=str(source_name),
            )
        )
    mappings = cluster_variants(
        evidence, min_support=min_support, min_similarity=min_similarity
    )
    result = pd.DataFrame(
        {
            "variant": [item.variant for item in mappings],
            "canonical": [item.canonical for item in mappings],
            "cluster_size": [item.cluster_size for item in mappings],
            "direct_support": [item.direct_support for item in mappings],
            "sources": [list(item.sources) for item in mappings],
            "min_support": min_support,
            "min_similarity": min_similarity,
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    if result.empty:
        schema = pa.schema(
            [
                ("variant", pa.string()),
                ("canonical", pa.string()),
                ("cluster_size", pa.int64()),
                ("direct_support", pa.int64()),
                ("sources", pa.list_(pa.string())),
                ("min_support", pa.int64()),
                ("min_similarity", pa.float64()),
            ]
        )
        pq.write_table(pa.Table.from_pylist([], schema=schema), output)
    else:
        result.to_parquet(output, index=False)
    return len(result)


def resolve_family_surnames(source: Path, output: Path) -> int:
    """Emit external final tokens absent from a shorter linked roll name.

    Args:
        source: Unified accepted-link artifact.
        output: Family-surname evidence artifact.

    Returns:
        Number of family-surname candidates written.

    Notes:
        This baseline requires an accepted omission-eligible link, a resolvable
        external final token, more external than roll eligible tokens, and the
        external token's absence from the roll. It does not overwrite the
        recorded surname.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema(
        [
            ("source", pa.string()),
            ("link_tier", pa.string()),
            ("link_id", pa.string()),
            ("roll_id", pa.string()),
            ("roll_name_raw", pa.string()),
            ("external_name_raw", pa.string()),
            ("recorded_surname", pa.string()),
            ("recorded_surname_raw", pa.string()),
            ("family_surname", pa.string()),
            ("family_surname_raw", pa.string()),
            ("family_surname_provenance", pa.string()),
            ("family_surname_score", pa.float64()),
        ]
    )
    writer = pq.ParquetWriter(output, schema, compression="zstd")
    row_count = 0
    try:
        parquet = pq.ParquetFile(source)
        for batch in parquet.iter_batches(batch_size=50_000):
            rows: list[dict[str, object]] = []
            for link in batch.to_pandas().itertuples(index=False):
                if not link.omission_eligible:
                    continue
                roll = extract_surname_candidates(link.roll_name_raw)
                external = extract_surname_candidates(link.external_name_raw)
                if external.surname is None:
                    continue
                roll_tokens = {token.normalized for token in roll.eligible_tokens}
                if len(external.eligible_tokens) <= len(roll.eligible_tokens):
                    continue
                if external.surname.normalized in roll_tokens:
                    continue
                rows.append(
                    {
                        "source": link.source,
                        "link_tier": link.link_tier,
                        "link_id": link.link_id,
                        "roll_id": link.roll_id,
                        "roll_name_raw": link.roll_name_raw,
                        "external_name_raw": link.external_name_raw,
                        "recorded_surname": (
                            None if roll.surname is None else roll.surname.normalized
                        ),
                        "recorded_surname_raw": (
                            None if roll.surname is None else roll.surname.raw
                        ),
                        "family_surname": external.surname.normalized,
                        "family_surname_raw": external.surname.raw,
                        "family_surname_provenance": "ration_card",
                        "family_surname_score": None,
                    }
                )
            if rows:
                table = pa.Table.from_pylist(rows, schema=schema)
                writer.write_table(table)
                row_count += table.num_rows
    finally:
        writer.close()
    return row_count


def evaluate_outputs(
    candidate_paths: list[Path],
    links_path: Path,
    alignments_path: Path,
    variants_path: Path,
    linked_resolved_path: Path,
    family_path: Path,
    *,
    state_positions: Mapping[str, SurnamePosition],
) -> pd.DataFrame:
    """Compute weighted state and accepted-link diagnostics.

    Args:
        candidate_paths: State candidate artifacts.
        links_path: Accepted source links.
        alignments_path: Token alignment operations.
        variants_path: Variant mapping artifact.
        linked_resolved_path: Recorded surnames for accepted person links.
        family_path: Family-surname evidence artifact.
        state_positions: Approved surname-token position by state.

    Returns:
        Long-form metric table.

    Raises:
        ValueError: If a state candidate artifact is empty.
    """
    rows: list[dict[str, object]] = []
    for path in candidate_paths:
        parquet = pq.ParquetFile(path)
        state: str | None = None
        denominator = 0
        resolved_weight = 0
        single_weight = 0
        first_relative_weight = 0
        last_relative_weight = 0
        selected_relative_weight = 0
        disagreement_weight = 0
        overlap_weights: Counter[str] = Counter()
        for batch in parquet.iter_batches(
            columns=[
                "state",
                "weight",
                "abstained",
                "abstention_reason",
                "first_candidate",
                "last_candidate",
                "first_in_relative",
                "last_in_relative",
            ]
        ):
            frame = batch.to_pandas()
            state = state or str(frame["state"].iloc[0])
            weight = frame["weight"].astype("int64")
            denominator += int(weight.sum())
            resolved_weight += int(weight[~frame["abstained"]].sum())
            single_weight += int(
                weight[frame["abstention_reason"] == "single-token-name"].sum()
            )
            first_relative_weight += int(weight[frame["first_in_relative"]].sum())
            last_relative_weight += int(weight[frame["last_in_relative"]].sum())
            position = state_positions.get(state)
            if position is None:
                raise ValueError(f"candidate state has no resolver policy: {state}")
            selected_relative_weight += int(
                weight[frame[f"{position}_in_relative"]].sum()
            )
            distinct = ~frame["abstained"] & frame["first_candidate"].ne(
                frame["last_candidate"]
            ).fillna(False)
            disagreement_weight += int(weight[distinct].sum())
            first_in = frame["first_in_relative"]
            last_in = frame["last_in_relative"]
            overlap_masks = {
                "first_only": distinct & first_in & ~last_in,
                "last_only": distinct & ~first_in & last_in,
                "both": distinct & first_in & last_in,
                "neither": distinct & ~first_in & ~last_in,
            }
            for category, mask in overlap_masks.items():
                overlap_weights[category] += int(weight[mask].sum())
        if state is None or denominator == 0:
            raise ValueError(f"candidate artifact is empty: {path}")
        metrics = {
            "weighted_records": denominator,
            "recorded_surname_coverage": resolved_weight / denominator,
            "single_token_share": single_weight / denominator,
            "first_in_relative_share": first_relative_weight / denominator,
            "last_in_relative_share": last_relative_weight / denominator,
            "selected_in_relative_share": selected_relative_weight / denominator,
            "first_last_disagreement_share": disagreement_weight / denominator,
            **{
                f"exact_relative_overlap_{category}_share": value / denominator
                for category, value in overlap_weights.items()
            },
        }
        rows.extend(
            {"scope": state, "metric": metric, "value": value}
            for metric, value in metrics.items()
        )
    link_counts: Counter[tuple[str, str, str]] = Counter()
    exact_counts: Counter[tuple[str, str, str]] = Counter()
    links_parquet = pq.ParquetFile(links_path)
    for batch in links_parquet.iter_batches(
        columns=["source", "link_tier", "sex", "name_exact_upstream"]
    ):
        for link in batch.to_pandas().itertuples(index=False):
            source_name = str(link.source)
            tier = str(link.link_tier)
            sex = _sex_group(link.sex)
            for group in ("all", sex):
                key = (source_name, tier, group)
                link_counts[key] += 1
                exact_counts[key] += int(link.name_exact_upstream)
    for (source_name, tier, sex), count in sorted(link_counts.items()):
        base_scope = f"{source_name}:{tier}"
        scope = base_scope if sex == "all" else f"{base_scope}:sex={sex}"
        rows.extend(
            [
                {"scope": scope, "metric": "accepted_links", "value": count},
                {
                    "scope": scope,
                    "metric": "upstream_exact_name_share",
                    "value": exact_counts[(source_name, tier, sex)] / count,
                },
            ]
        )
    operation_counts: Counter[str] = Counter()
    alignments_parquet = pq.ParquetFile(alignments_path)
    for batch in alignments_parquet.iter_batches(columns=["kind"]):
        operation_counts.update(batch.column(0).to_pylist())
    for operation, count in sorted(operation_counts.items()):
        rows.append(
            {"scope": "all_links", "metric": f"alignment_{operation}", "value": count}
        )
    resolution_counts: Counter[tuple[str, str, str, str]] = Counter()
    resolution_totals: Counter[tuple[str, str, str]] = Counter()
    resolved_parquet = pq.ParquetFile(linked_resolved_path)
    for batch in resolved_parquet.iter_batches(
        columns=["source", "link_tier", "sex", "surname_provenance", "abstained"]
    ):
        for result in batch.to_pandas().itertuples(index=False):
            source_name = str(result.source)
            tier = str(result.link_tier)
            sex = _sex_group(result.sex)
            if result.abstained:
                category = "abstained"
            elif str(result.surname_provenance).endswith("_segmentation"):
                category = "segmented"
            else:
                category = "written"
            for group in ("all", sex):
                key = (source_name, tier, group)
                resolution_totals[key] += 1
                resolution_counts[(*key, category)] += 1
    for (source_name, tier, sex), total in sorted(resolution_totals.items()):
        base_scope = f"{source_name}:{tier}"
        scope = base_scope if sex == "all" else f"{base_scope}:sex={sex}"
        rows.extend(
            {
                "scope": scope,
                "metric": f"linked_resolution_{category}_share",
                "value": resolution_counts[(source_name, tier, sex, category)] / total,
            }
            for category in ("written", "segmented", "abstained")
        )
    variants = pq.ParquetFile(variants_path).metadata.num_rows
    family = pq.ParquetFile(family_path).metadata.num_rows
    rows.append({"scope": "all_links", "metric": "variant_mappings", "value": variants})
    rows.append(
        {"scope": "all_links", "metric": "family_surname_candidates", "value": family}
    )
    return pd.DataFrame(rows)
