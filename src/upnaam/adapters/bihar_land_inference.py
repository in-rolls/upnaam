"""Infer Bihar land surnames after exact administrative suffixes."""

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


BIHAR_LAND_INFERENCE_REVISION = "bihar-land-record-suffix-inference-v1"
BIHAR_LAND_RECORD_SUFFIXES = frozenset(
    {
        "अन्य",
        "बगेरह",
        "बगैरह",
        "वगै",
        "वगै0",
        "वगैरा",
        "वगैरह",
        "वगेरह",
        "वोगैरह",
        "वैगरह",
    }
)
BIHAR_LAND_INFERENCE_SOURCE = "bihar_land_distinct_official_name_vocabulary"

BIHAR_LAND_INFERRED_SCHEMA = pa.schema(
    [
        ("surname_inferred_normalized", pa.string()),
        ("surname_inferred_raw_mode", pa.string()),
        ("surname_inferred_raw_mode_count", pa.int64()),
        ("raw_variant_count", pa.int64()),
        ("distinct_full_name_count", pa.int64()),
        ("written_final_token_count", pa.int64()),
        ("record_suffix_adjusted_count", pa.int64()),
        ("inference_source", pa.string()),
        ("normalization_revision", pa.string()),
        ("inference_revision", pa.string()),
    ]
)


@dataclass(frozen=True, slots=True)
class BiharLandInferenceReport:
    """Non-identifying diagnostics for suffix-adjusted land surnames."""

    source_rows: int
    nonnull_name_rows: int
    distinct_source_names: int
    inferred_names: int
    abstained_names: int
    distinct_inferred_surnames: int
    written_final_token_names: int
    record_suffix_adjusted_names: int
    adjustments_by_suffix: dict[str, int]
    abstentions_by_reason: dict[str, int]


def _mode(raw_counts: Mapping[str, int]) -> tuple[str, int]:
    """Choose the most frequent raw value, breaking ties lexicographically."""
    return min(raw_counts.items(), key=lambda item: (-item[1], item[0]))


def infer_bihar_land_surname_counts(
    input_path: Path,
    output_path: Path,
    *,
    name_column: str = "name_of_ryot",
    batch_size: int = 100_000,
) -> BiharLandInferenceReport:
    """Group inferred surnames after exact source-specific record suffixes.

    Args:
        input_path: Parquet table containing one row per distinct source name.
        output_path: Destination for the typed inferred-surname aggregate.
        name_column: Column containing the untouched official full name.
        batch_size: Maximum names processed in one iteration.

    Returns:
        Aggregate inference coverage, provenance counts, and abstentions.

    Raises:
        ValueError: If the input column is absent, non-textual, duplicated, or
            ``batch_size`` is invalid.
        BaseException: After removing an incomplete temporary output.

    Notes:
        Only an exact normalized match to ``BIHAR_LAND_RECORD_SUFFIXES`` moves
        selection to the preceding eligible token. There is no fuzzy suffix
        recognition. Counts represent distinct written full-name strings.
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
    written_counts: Counter[str] = Counter()
    adjusted_counts: Counter[str] = Counter()
    suffix_counts: Counter[str] = Counter()
    abstentions: Counter[str] = Counter()
    for batch in table.to_batches(max_chunksize=batch_size):
        for name in batch.column(0).to_pylist():
            selected = extract_surname_candidates(name)
            if selected.surname is None:
                abstentions[selected.abstention_reason or "unknown"] += 1
                continue
            written = selected.surname
            if written.normalized in BIHAR_LAND_RECORD_SUFFIXES:
                inferred = selected.eligible_tokens[-2]
                adjusted_counts[inferred.normalized] += 1
                suffix_counts[written.normalized] += 1
            else:
                inferred = written
                written_counts[inferred.normalized] += 1
            surname_counts[inferred.normalized] += 1
            raw_counts[inferred.normalized][inferred.raw] += 1

    rows: list[dict[str, object]] = []
    for normalized, count in surname_counts.items():
        raw_mode, raw_mode_count = _mode(raw_counts[normalized])
        rows.append(
            {
                "surname_inferred_normalized": normalized,
                "surname_inferred_raw_mode": raw_mode,
                "surname_inferred_raw_mode_count": raw_mode_count,
                "raw_variant_count": len(raw_counts[normalized]),
                "distinct_full_name_count": count,
                "written_final_token_count": written_counts[normalized],
                "record_suffix_adjusted_count": adjusted_counts[normalized],
                "inference_source": BIHAR_LAND_INFERENCE_SOURCE,
                "normalization_revision": NORMALIZATION_REVISION,
                "inference_revision": BIHAR_LAND_INFERENCE_REVISION,
            }
        )
    rows.sort(
        key=lambda item: (
            -cast("int", item["distinct_full_name_count"]),
            cast("str", item["surname_inferred_normalized"]),
        )
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    try:
        pq.write_table(
            pa.Table.from_pylist(rows, schema=BIHAR_LAND_INFERRED_SCHEMA),
            temporary,
            compression="zstd",
        )
        temporary.replace(output_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    adjusted_names = sum(suffix_counts.values())
    inferred_names = sum(surname_counts.values())
    return BiharLandInferenceReport(
        source_rows=source_rows,
        nonnull_name_rows=nonnull_name_rows,
        distinct_source_names=distinct_source_names,
        inferred_names=inferred_names,
        abstained_names=sum(abstentions.values()),
        distinct_inferred_surnames=len(surname_counts),
        written_final_token_names=inferred_names - adjusted_names,
        record_suffix_adjusted_names=adjusted_names,
        adjustments_by_suffix=dict(sorted(suffix_counts.items())),
        abstentions_by_reason=dict(sorted(abstentions.items())),
    )


def write_bihar_land_inference_audit(
    path: Path, report: BiharLandInferenceReport
) -> None:
    """Write aggregate suffix-adjusted inference diagnostics as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(asdict(report), stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)
