"""Aggregate written final tokens from distinct Bihar land-record names."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, cast

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from upnaam.normalization import NORMALIZATION_REVISION
from upnaam.selection import extract_surname_candidates

if TYPE_CHECKING:
    from collections.abc import Mapping
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


def _mode(raw_counts: Mapping[str, int]) -> tuple[str, int]:
    """Choose the most frequent raw value, breaking ties lexicographically."""
    return min(raw_counts.items(), key=lambda item: (-item[1], item[0]))


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
        BaseException: After removing an incomplete temporary output.

    Notes:
        Counts represent distinct written full-name strings, not people,
        holdings, accounts, or land-record rows.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least one")
    parquet = pq.ParquetFile(input_path)
    if name_column not in parquet.schema_arrow.names:
        raise ValueError(f"Bihar land names are missing column: {name_column}")
    field = parquet.schema_arrow.field(name_column)
    if not (pa.types.is_string(field.type) or pa.types.is_large_string(field.type)):
        raise ValueError("Bihar land name column must have a string type")

    table = parquet.read(columns=[name_column])
    names = table.column(name_column)
    source_rows = len(names)
    nonnull_name_rows = source_rows - names.null_count
    distinct_source_names = cast(
        "int", pc.call_function("count_distinct", [names]).as_py()
    )
    if distinct_source_names != nonnull_name_rows:
        raise ValueError("Bihar land input must contain distinct nonnull names")

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
        raw_mode, raw_mode_count = _mode(raw_counts[normalized])
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    try:
        pq.write_table(
            pa.Table.from_pylist(rows, schema=BIHAR_LAND_AGGREGATE_SCHEMA),
            temporary,
            compression="zstd",
        )
        temporary.replace(output_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

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
