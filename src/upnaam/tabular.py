"""Tabular stage implementations for electoral name records."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from upnaam.normalization import normalize_name

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

NAME_COLUMNS = ("english_name", "father_husband_name", "n_times")
_PREFIX_PATTERN = re.compile(
    r"^(?:(?:श्री|श्रीमती|सुश्री|डॉ|shri|sri|srimati|smt|mr|mrs|ms|dr)\s+)+",
    flags=re.IGNORECASE,
)
_ENGLISH_LETTER_PATTERN = r"[A-Za-z]"


def _write_frames(frames: Iterable[pd.DataFrame], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    rows = 0
    try:
        for frame in frames:
            table = pa.Table.from_pandas(frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(output, table.schema, compression="zstd")
            writer.write_table(table)
            rows += len(frame)
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        raise ValueError("stage produced no rows")
    return rows


def normalize_electoral_name_table(
    source: Path,
    output: Path,
    *,
    state: str,
    chunksize: int = 100_000,
) -> int:
    """Normalize one aggregated state electoral-name table.

    Args:
        source: Compressed CSV containing the three expected name columns.
        output: Destination Parquet artifact.
        state: Lowercase state identifier.
        chunksize: CSV rows processed per batch.

    Returns:
        Number of rows written.
    """

    def normalized_frames() -> Iterable[pd.DataFrame]:
        source_row = 0
        for chunk in pd.read_csv(source, chunksize=chunksize, dtype="string"):
            missing = set(NAME_COLUMNS).difference(chunk.columns)
            if missing:
                raise ValueError(f"{source} is missing columns: {sorted(missing)}")
            frame = pd.DataFrame(
                {
                    "source": "electoral_roll_aggregate",
                    "state": state,
                    "source_row": range(source_row, source_row + len(chunk)),
                    "name_raw": chunk["english_name"],
                    "relative_name_raw": chunk["father_husband_name"],
                    "weight": pd.to_numeric(chunk["n_times"], errors="raise").astype(
                        "int64"
                    ),
                }
            )
            frame["name_normalized"] = frame["name_raw"].map(normalize_name)
            frame["relative_name_normalized"] = frame["relative_name_raw"].map(
                normalize_name
            )
            yield frame
            source_row += len(frame)

    return _write_frames(normalized_frames(), output)


def _candidate_frame(frame: pd.DataFrame) -> pd.DataFrame:
    raw_name = frame["name_raw"].astype("string")
    raw_cleaned = raw_name.str.replace(_PREFIX_PATTERN, "", regex=True)
    normalized_cleaned = (
        frame["name_normalized"]
        .astype("string")
        .str.replace(_PREFIX_PATTERN, "", regex=True)
    )
    normalized_tokens = normalized_cleaned.str.split(expand=True)
    if normalized_tokens.shape[1] == 0:
        raise ValueError("candidate batch contains no token columns")
    raw_tokens = raw_cleaned.str.split(expand=True).reindex(
        columns=normalized_tokens.columns
    )
    eligible = normalized_tokens.apply(
        lambda column: column.str.count(_ENGLISH_LETTER_PATTERN) >= 2
    ).fillna(False)
    eligible_values = eligible.to_numpy(dtype=bool)
    eligible_count = eligible_values.sum(axis=1)
    first_index = eligible_values.argmax(axis=1)
    last_index = eligible_values.shape[1] - 1 - eligible_values[:, ::-1].argmax(axis=1)
    row_index = np.arange(len(frame))
    normalized_values = normalized_tokens.fillna("").to_numpy(dtype=str)
    raw_values = raw_tokens.fillna("").to_numpy(dtype=str)
    first_values = normalized_values[row_index, first_index]
    last_values = normalized_values[row_index, last_index]
    first_raw_values = raw_values[row_index, first_index]
    last_raw_values = raw_values[row_index, last_index]
    has_candidate = eligible_count > 0
    first = pd.Series(first_values, index=frame.index, dtype="string").where(
        has_candidate
    )
    last = pd.Series(last_values, index=frame.index, dtype="string").where(
        has_candidate
    )
    first_raw = pd.Series(first_raw_values, index=frame.index, dtype="string").where(
        has_candidate
    )
    last_raw = pd.Series(last_raw_values, index=frame.index, dtype="string").where(
        has_candidate
    )
    relative_tokens = (
        frame["relative_name_normalized"].astype("string").str.split(expand=True)
    )
    if relative_tokens.shape[1] == 0:
        first_in_relative = pd.Series(False, index=frame.index)
        last_in_relative = pd.Series(False, index=frame.index)
    else:
        relative_values = relative_tokens.fillna("").to_numpy(dtype=str)
        first_in_relative = pd.Series(
            (relative_values == first_values[:, None]).any(axis=1) & has_candidate,
            index=frame.index,
        )
        last_in_relative = pd.Series(
            (relative_values == last_values[:, None]).any(axis=1) & has_candidate,
            index=frame.index,
        )
    resolved = eligible_count >= 2
    missing_name = raw_name.isna() | raw_name.str.strip().eq("")
    reason = pd.Series(pd.NA, index=frame.index, dtype="string")
    reason.loc[eligible_count == 0] = "no-eligible-token"
    reason.loc[missing_name] = "missing-name"
    reason.loc[eligible_count == 1] = "single-token-name"
    candidates = pd.DataFrame(index=frame.index)
    candidates["first_candidate"] = first
    candidates["first_candidate_raw"] = first_raw
    candidates["last_candidate"] = last
    candidates["last_candidate_raw"] = last_raw
    candidates["baseline_surname"] = last.where(resolved)
    candidates["baseline_surname_raw"] = last_raw.where(resolved)
    candidates["baseline_position"] = pd.Series(
        "last", index=frame.index, dtype="string"
    ).where(resolved)
    candidates["abstained"] = ~resolved
    candidates["abstention_reason"] = reason
    candidates["first_in_relative"] = first_in_relative
    candidates["last_in_relative"] = last_in_relative
    return pd.concat(
        [frame.reset_index(drop=True), candidates.reset_index(drop=True)], axis=1
    )


def extract_candidate_table(source: Path, output: Path) -> int:
    """Add transparent positional surname candidates to normalized records.

    Args:
        source: Normalized electoral-name Parquet artifact.
        output: Candidate Parquet artifact.

    Returns:
        Number of rows written.
    """
    parquet = pq.ParquetFile(source)

    def candidate_frames() -> Iterable[pd.DataFrame]:
        for batch in parquet.iter_batches(batch_size=100_000):
            frame = batch.to_pandas()
            yield _candidate_frame(frame)

    return _write_frames(candidate_frames(), output)


def resolve_recorded_surnames(
    source: Path,
    output: Path,
    *,
    variants: dict[str, str] | None = None,
) -> int:
    """Resolve the approved final-token baseline with optional variants.

    Args:
        source: Candidate table.
        output: Recorded-surname result table.
        variants: Evidence-backed normalized variant mappings.

    Returns:
        Number of rows written.
    """
    variant_map = variants or {}
    parquet = pq.ParquetFile(source)

    def resolved_frames() -> Iterable[pd.DataFrame]:
        for batch in parquet.iter_batches(batch_size=100_000):
            frame = batch.to_pandas()
            resolved = frame["baseline_surname"].map(
                lambda value: (
                    variant_map.get(value, value) if isinstance(value, str) else None
                )
            )
            result = frame.loc[
                :,
                [
                    "source",
                    "state",
                    "source_row",
                    "name_raw",
                    "relative_name_raw",
                    "weight",
                    "abstained",
                    "abstention_reason",
                ],
            ].copy()
            result["surname"] = resolved
            result["surname_raw"] = frame["baseline_surname_raw"]
            result["surname_position"] = frame["baseline_position"]
            result["surname_provenance"] = resolved.map(
                lambda value: "written_final_token" if isinstance(value, str) else None
            )
            result["surname_score"] = pd.Series([None] * len(result), dtype="Float64")
            yield result

    return _write_frames(resolved_frames(), output)


def load_variant_map(path: Path) -> dict[str, str]:
    """Load a variant mapping from Parquet or JSON.

    Args:
        path: Variant artifact.

    Returns:
        Variant-to-canonical dictionary.
    """
    if path.suffix == ".parquet":
        frame = pd.read_parquet(path, columns=["variant", "canonical"])
        return dict(zip(frame["variant"], frame["canonical"], strict=True))
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    return {item["variant"]: item["canonical"] for item in payload}
