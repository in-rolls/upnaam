"""Shared storage validation and schema fields for source adapters."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

SURNAME_FIELDS = [
    ("surname_raw", pa.string()),
    ("surname_source_normalized", pa.string()),
    ("surname_latin_raw", pa.string()),
    ("surname_latin_normalized", pa.string()),
    ("surname_canonical", pa.string()),
    ("canonicalization_status", pa.string()),
    ("canonicalization_reason", pa.string()),
    ("canonicalization_provenance", pa.string()),
    ("canonicalization_revision", pa.string()),
    ("surname_position", pa.string()),
    ("surname_provenance", pa.string()),
]

LINK_COLUMNS = frozenset(
    {
        "source",
        "link_tier",
        "link_id",
        "roll_id",
        "external_id",
        "roll_name_raw",
        "external_name_raw",
        "relation_type",
        "sex",
        "name_exact_upstream",
    }
)


def choose_raw_mode(raw_counts: Mapping[str, int]) -> tuple[str, int]:
    """Choose the most frequent value, breaking ties lexicographically."""
    return min(raw_counts.items(), key=lambda item: (-item[1], item[0]))


def read_distinct_land_names(
    input_path: Path, name_column: str
) -> tuple[pa.Table, int, int, int]:
    """Read and validate the distinct Bihar land-name vocabulary.

    Args:
        input_path: Source Parquet file.
        name_column: Text column containing official names.

    Returns:
        Name table, row count, nonnull count, and distinct count.

    Raises:
        ValueError: If the column or distinctness is invalid.
    """
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
    return table, source_rows, nonnull_name_rows, distinct_source_names


def write_audit(path: Path, report: Mapping[str, object]) -> None:
    """Write aggregate diagnostic fields as JSON through a temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)


def write_rows_parquet(
    rows: list[dict[str, object]], schema: pa.Schema, output_path: Path
) -> None:
    """Write rows to zstd Parquet through a temporary file, removed on failure.

    Args:
        rows: Records matching the schema.
        schema: Arrow schema for the written table.
        output_path: Destination Parquet path.

    Raises:
        BaseException: After removing an incomplete temporary output.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    try:
        pq.write_table(
            pa.Table.from_pylist(rows, schema=schema),
            temporary,
            compression="zstd",
        )
        temporary.replace(output_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
