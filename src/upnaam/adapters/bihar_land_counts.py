"""Aggregate written final tokens from distinct Bihar land-record names."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, cast

import pyarrow as pa

from upnaam.adapters._shared import (
    choose_raw_mode,
    read_distinct_land_names,
    write_rows_parquet,
)
from upnaam.normalization import NORMALIZATION_REVISION
from upnaam.selection import extract_surname_candidates

if TYPE_CHECKING:
    from pathlib import Path


BIHAR_LAND_AGGREGATE_REVISION = "bihar-land-written-surname-counts-v1"
BIHAR_LAND_PROVENANCE = "bihar_land_written_final_token"

BIHAR_LAND_AGGREGATE_SCHEMA = pa.schema(
    [
        ("surname_source_normalized", pa.string()),
        ("surname_raw_mode", pa.string()),
        ("surname_raw_mode_count", pa.int64()),
        ("raw_variant_count", pa.int64()),
        ("distinct_full_name_count", pa.int64()),
        ("surname_provenance", pa.string()),
        ("normalization_revision", pa.string()),
        ("aggregate_revision", pa.string()),
    ]
)


@dataclass(frozen=True, slots=True)
class BiharLandAggregateReport:
    """Non-identifying diagnostics for the Bihar land-name vocabulary."""

    source_rows: int
    nonnull_name_rows: int
    distinct_source_names: int
    selected_names: int
    abstained_names: int
    distinct_surnames: int
    abstentions_by_reason: dict[str, int]


def build_bihar_land_surname_counts(
    input_path: Path,
    output_path: Path,
    *,
    name_column: str = "name_of_ryot",
    batch_size: int = 100_000,
) -> BiharLandAggregateReport:
    """Group final eligible tokens across distinct official ryot names.

    Args:
        input_path: Parquet table containing one row per distinct source name.
        output_path: Destination for the typed grouped-token artifact.
        name_column: Column containing the untouched official full name.
        batch_size: Maximum names processed in one iteration.

    Returns:
        Aggregate selection coverage and abstention diagnostics.

    Raises:
        ValueError: If the input column is absent, non-textual, duplicated, or
            ``batch_size`` is invalid.

    Notes:
        Counts represent distinct written full-name strings, not people,
        holdings, accounts, or land-record rows.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least one")
    table, source_rows, nonnull_name_rows, distinct_source_names = (
        read_distinct_land_names(input_path, name_column)
    )

    surname_counts: Counter[str] = Counter()
    raw_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    abstentions: Counter[str] = Counter()
    for batch in table.to_batches(max_chunksize=batch_size):
        for name in batch.column(0).to_pylist():
            selected = extract_surname_candidates(name)
            if selected.surname is None:
                abstentions[selected.abstention_reason or "unknown"] += 1
                continue
            normalized = selected.surname.normalized
            surname_counts[normalized] += 1
            raw_counts[normalized][selected.surname.raw] += 1

    rows: list[dict[str, object]] = []
    for normalized, count in surname_counts.items():
        raw_mode, raw_mode_count = choose_raw_mode(raw_counts[normalized])
        rows.append(
            {
                "surname_source_normalized": normalized,
                "surname_raw_mode": raw_mode,
                "surname_raw_mode_count": raw_mode_count,
                "raw_variant_count": len(raw_counts[normalized]),
                "distinct_full_name_count": count,
                "surname_provenance": BIHAR_LAND_PROVENANCE,
                "normalization_revision": NORMALIZATION_REVISION,
                "aggregate_revision": BIHAR_LAND_AGGREGATE_REVISION,
            }
        )
    rows.sort(
        key=lambda item: (
            -cast("int", item["distinct_full_name_count"]),
            cast("str", item["surname_source_normalized"]),
        )
    )

    write_rows_parquet(rows, BIHAR_LAND_AGGREGATE_SCHEMA, output_path)

    selected_names = sum(surname_counts.values())
    return BiharLandAggregateReport(
        source_rows=source_rows,
        nonnull_name_rows=nonnull_name_rows,
        distinct_source_names=distinct_source_names,
        selected_names=selected_names,
        abstained_names=sum(abstentions.values()),
        distinct_surnames=len(surname_counts),
        abstentions_by_reason=dict(sorted(abstentions.items())),
    )


def write_bihar_land_aggregate_audit(
    path: Path, report: BiharLandAggregateReport
) -> None:
    """Write aggregate Bihar land-name diagnostics as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(asdict(report), stream, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)
