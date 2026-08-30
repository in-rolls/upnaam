"""Elector-level Punjab surname artifact construction."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from csv import DictWriter
from dataclasses import dataclass
from itertools import zip_longest
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from upnaam.normalization import (
    NORMALIZATION_REVISION,
    normalize_latin_token,
    tokenize_name,
)
from upnaam.schema import CANONICALIZATION_REVISION, CanonicalizationStatus
from upnaam.selection import extract_surname_candidates

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

PUNJAB_RESOLVER_REVISION = "punjab-elector-resolver-v1"
PUNJAB_TRANSLITERATION_REVISION = "indicate-punjab-gpt4o-v1"
PUNJAB_SOURCE_REVISION = "dataverse-muegdt-v25.0"

RAW_COLUMNS = (
    "id",
    "number",
    "elector_name",
    "father_or_husband_name",
    "relationship",
    "house_no",
    "age",
    "sex",
    "ac_name",
    "parl_constituency",
    "part_no",
    "year",
    "state",
    "filename",
    "main_town",
    "police_station",
    "mandal",
    "revenue_division",
    "district",
    "polling_station_name",
    "polling_station_address",
)
TRANSLITERATED_NATIVE_COLUMNS = (
    "elector_name",
    "father_or_husband_name",
    "ac_name",
    "parl_constituency",
    "main_town",
    "police_station",
    "mandal",
    "revenue_division",
    "district",
    "polling_station_name",
    "polling_station_address",
)
TRANSLITERATED_COLUMNS = tuple(
    f"{column}_transliterated" for column in TRANSLITERATED_NATIVE_COLUMNS
)

PUNJAB_OUTPUT_SCHEMA = pa.schema(
    [
        ("source_row", pa.int64()),
        ("elector_id", pa.string()),
        ("source_elector_id", pa.string()),
        ("source_number", pa.string()),
        ("state", pa.string()),
        ("year", pa.string()),
        ("filename", pa.string()),
        ("part_no", pa.string()),
        ("house_no_raw", pa.string()),
        ("age_raw", pa.string()),
        ("sex_raw", pa.string()),
        ("relationship_raw", pa.string()),
        ("name_native_raw", pa.string()),
        ("name_latin_raw", pa.string()),
        ("relative_name_native_raw", pa.string()),
        ("relative_name_latin_raw", pa.string()),
        ("ac_name_native_raw", pa.string()),
        ("ac_name_latin_raw", pa.string()),
        ("parl_constituency_native_raw", pa.string()),
        ("parl_constituency_latin_raw", pa.string()),
        ("main_town_native_raw", pa.string()),
        ("main_town_latin_raw", pa.string()),
        ("district_native_raw", pa.string()),
        ("district_latin_raw", pa.string()),
        ("surname_raw", pa.string()),
        ("surname_source_normalized", pa.string()),
        ("surname_latin_raw", pa.string()),
        ("surname_latin_normalized", pa.string()),
        ("surname_canonical", pa.string()),
        ("canonicalization_status", pa.string()),
        ("canonicalization_provenance", pa.string()),
        ("canonicalization_revision", pa.string()),
        ("surname_position", pa.string()),
        ("surname_provenance", pa.string()),
        ("abstained", pa.bool_()),
        ("abstention_reason", pa.string()),
        ("transliteration_status", pa.string()),
        ("normalization_revision", pa.string()),
        ("resolver_revision", pa.string()),
        ("transliteration_revision", pa.string()),
    ]
)


@dataclass(frozen=True, slots=True)
class PunjabSurnameResult:
    """Resolution of a native/Latin name pair under the Punjab baseline."""

    surname_raw: str | None
    surname_source_normalized: str | None
    surname_latin_raw: str | None
    surname_latin_normalized: str | None
    abstained: bool
    abstention_reason: str | None
    transliteration_status: str


@dataclass(frozen=True, slots=True)
class PunjabArtifactReport:
    """Aggregate contract checks returned by the Punjab artifact builder."""

    rows: int
    abstention_reasons: Mapping[str, int]
    transliteration_statuses: Mapping[str, int]
    by_sex: Mapping[str, Mapping[str, int]]
    by_relationship: Mapping[str, Mapping[str, int]]
    top_surnames: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "rows": self.rows,
            "resolved_native": self.rows - sum(self.abstention_reasons.values()),
            "abstained": sum(self.abstention_reasons.values()),
            "abstention_reasons": dict(sorted(self.abstention_reasons.items())),
            "transliteration_statuses": dict(
                sorted(self.transliteration_statuses.items())
            ),
            "by_sex": {
                key: dict(sorted(value.items()))
                for key, value in sorted(self.by_sex.items())
            },
            "by_relationship": {
                key: dict(sorted(value.items()))
                for key, value in sorted(self.by_relationship.items())
            },
            "top_surnames": [
                {"surname": surname, "rows": rows}
                for surname, rows in self.top_surnames
            ],
        }


def resolve_punjab_name_pair(
    native_name: object, latin_name: object
) -> PunjabSurnameResult:
    """Resolve the final eligible token and its aligned Latin transcription.

    The surname decision is made only from the native roll name. Latin text is
    copied from the same token position when the two complete token sequences
    have equal length. Unequal sequences never receive a guessed Latin token.

    Args:
        native_name: Original Gurmukhi elector name.
        latin_name: Indicate's aligned full-name transcription.

    Returns:
        Native selection, optional Latin transcription, and explicit statuses.
    """
    candidates = extract_surname_candidates(native_name)
    if candidates.abstained:
        return PunjabSurnameResult(
            surname_raw=None,
            surname_source_normalized=None,
            surname_latin_raw=None,
            surname_latin_normalized=None,
            abstained=True,
            abstention_reason=candidates.abstention_reason,
            transliteration_status="no-surname-selected",
        )
    selected = candidates.eligible_tokens[-1]
    native_index = candidates.tokens.index(selected)
    latin_tokens = tokenize_name(latin_name)
    if len(latin_tokens) != len(candidates.tokens):
        return PunjabSurnameResult(
            surname_raw=selected.raw,
            surname_source_normalized=selected.normalized,
            surname_latin_raw=None,
            surname_latin_normalized=None,
            abstained=False,
            abstention_reason=None,
            transliteration_status="token-count-mismatch",
        )
    latin_token = latin_tokens[native_index]
    normalized_latin = normalize_latin_token(latin_token.raw)
    if latin_token.letter_count < 2 or normalized_latin is None:
        return PunjabSurnameResult(
            surname_raw=selected.raw,
            surname_source_normalized=selected.normalized,
            surname_latin_raw=None,
            surname_latin_normalized=None,
            abstained=False,
            abstention_reason=None,
            transliteration_status="ineligible-latin-token",
        )
    return PunjabSurnameResult(
        surname_raw=selected.raw,
        surname_source_normalized=selected.normalized,
        surname_latin_raw=latin_token.raw,
        surname_latin_normalized=normalized_latin,
        abstained=False,
        abstention_reason=None,
        transliteration_status="aligned",
    )


def _nullable_string(series: pd.Series) -> pd.Series:
    stripped = series.astype("string")
    return stripped.mask(stripped.eq(""), pd.NA)


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    column = frame[name]
    if isinstance(column, pd.DataFrame):
        raise ValueError(f"duplicate column in source artifact: {name}")
    return column


def _companion_frames(path: Path, *, batch_size: int) -> Iterator[pd.DataFrame]:
    parquet = pq.ParquetFile(path)
    required = set(TRANSLITERATED_NATIVE_COLUMNS + TRANSLITERATED_COLUMNS)
    missing = required.difference(parquet.schema_arrow.names)
    if missing:
        raise ValueError(
            f"transliteration artifact is missing columns: {sorted(missing)}"
        )
    for batch in parquet.iter_batches(
        batch_size=batch_size,
        columns=list(TRANSLITERATED_NATIVE_COLUMNS + TRANSLITERATED_COLUMNS),
    ):
        yield batch.to_pandas()


def _validate_native_alignment(
    raw: pd.DataFrame, companion: pd.DataFrame, *, source_row: int
) -> None:
    for column in set(raw.columns).intersection(TRANSLITERATED_NATIVE_COLUMNS):
        raw_values = _column(raw, column).astype("string").fillna("")
        companion_values = _column(companion, column).astype("string").fillna("")
        unequal = raw_values.to_numpy() != companion_values.to_numpy()
        if unequal.any():
            offset = int(unequal.argmax())
            raise ValueError(
                f"native-field mismatch at source_row {source_row + offset} "
                f"for {column}"
            )


def _resolve_pairs(
    native: pd.Series,
    latin: pd.Series,
    cache: dict[tuple[object, object], PunjabSurnameResult],
) -> list[PunjabSurnameResult]:
    output: list[PunjabSurnameResult] = []
    for native_value, latin_value in zip(native, latin, strict=True):
        native_key: object = native_value if isinstance(native_value, str) else None
        latin_key: object = latin_value if isinstance(latin_value, str) else None
        key = (native_key, latin_key)
        result = cache.get(key)
        if result is None:
            result = resolve_punjab_name_pair(native_key, latin_key)
            cache[key] = result
        output.append(result)
    return output


def _update_strata(
    counts: dict[str, Counter[str]], labels: pd.Series, frame: pd.DataFrame
) -> None:
    normalized_labels = (
        labels.reset_index(drop=True).astype("string").str.strip().str.casefold()
    )
    normalized_labels = normalized_labels.fillna("missing").replace("", "missing")
    for label in normalized_labels.unique():
        selected = normalized_labels.eq(label)
        group = frame.loc[selected]
        counter = counts[str(label)]
        counter["rows"] += len(group)
        counter["native_resolved"] += int((~group["abstained"]).sum())
        counter["ascii_resolved"] += int(
            group["surname_latin_normalized"].notna().sum()
        )
        counter["abstained"] += int(group["abstained"].sum())
        for status, value in group["transliteration_status"].value_counts().items():
            counter[f"transliteration_{status}"] += int(value)


def _output_frame(
    raw: pd.DataFrame,
    companion: pd.DataFrame,
    *,
    source_row: int,
    cache: dict[tuple[object, object], PunjabSurnameResult],
) -> pd.DataFrame:
    raw = raw.reset_index(drop=True)
    companion = companion.reset_index(drop=True)
    latin_name = _nullable_string(_column(companion, "elector_name_transliterated"))
    native_name = _nullable_string(_column(raw, "elector_name"))
    results = _resolve_pairs(native_name, latin_name, cache)
    rows = range(source_row, source_row + len(raw))
    return pd.DataFrame(
        {
            "source_row": rows,
            "elector_id": [f"muegdt-v25-punjab:{row}" for row in rows],
            "source_elector_id": _nullable_string(_column(raw, "id")),
            "source_number": _nullable_string(_column(raw, "number")),
            "state": _nullable_string(_column(raw, "state")).str.casefold(),
            "year": _nullable_string(_column(raw, "year")),
            "filename": _nullable_string(_column(raw, "filename")),
            "part_no": _nullable_string(_column(raw, "part_no")),
            "house_no_raw": _nullable_string(_column(raw, "house_no")),
            "age_raw": _nullable_string(_column(raw, "age")),
            "sex_raw": _nullable_string(_column(raw, "sex")),
            "relationship_raw": _nullable_string(_column(raw, "relationship")),
            "name_native_raw": native_name,
            "name_latin_raw": latin_name,
            "relative_name_native_raw": _nullable_string(
                _column(raw, "father_or_husband_name")
            ),
            "relative_name_latin_raw": _nullable_string(
                _column(companion, "father_or_husband_name_transliterated")
            ),
            "ac_name_native_raw": _nullable_string(_column(raw, "ac_name")),
            "ac_name_latin_raw": _nullable_string(
                _column(companion, "ac_name_transliterated")
            ),
            "parl_constituency_native_raw": _nullable_string(
                _column(raw, "parl_constituency")
            ),
            "parl_constituency_latin_raw": _nullable_string(
                _column(companion, "parl_constituency_transliterated")
            ),
            "main_town_native_raw": _nullable_string(_column(raw, "main_town")),
            "main_town_latin_raw": _nullable_string(
                _column(companion, "main_town_transliterated")
            ),
            "district_native_raw": _nullable_string(_column(raw, "district")),
            "district_latin_raw": _nullable_string(
                _column(companion, "district_transliterated")
            ),
            "surname_raw": [result.surname_raw for result in results],
            "surname_source_normalized": [
                result.surname_source_normalized for result in results
            ],
            "surname_latin_raw": [result.surname_latin_raw for result in results],
            "surname_latin_normalized": [
                result.surname_latin_normalized for result in results
            ],
            "surname_canonical": [
                result.surname_latin_normalized for result in results
            ],
            "canonicalization_status": [
                (
                    CanonicalizationStatus.IDENTITY_UNMAPPED.value
                    if result.surname_latin_normalized is not None
                    else (
                        CanonicalizationStatus.NOT_APPLICABLE.value
                        if result.abstained
                        else CanonicalizationStatus.NORMALIZATION_UNAVAILABLE.value
                    )
                )
                for result in results
            ],
            "canonicalization_provenance": None,
            "canonicalization_revision": CANONICALIZATION_REVISION,
            "surname_position": [
                None if result.abstained else "last" for result in results
            ],
            "surname_provenance": [
                None if result.abstained else "written_final_token"
                for result in results
            ],
            "abstained": [result.abstained for result in results],
            "abstention_reason": [result.abstention_reason for result in results],
            "transliteration_status": [
                result.transliteration_status for result in results
            ],
            "normalization_revision": NORMALIZATION_REVISION,
            "resolver_revision": PUNJAB_RESOLVER_REVISION,
            "transliteration_revision": PUNJAB_TRANSLITERATION_REVISION,
        }
    )


def build_punjab_elector_artifact(
    roll_path: Path,
    transliteration_path: Path,
    output_path: Path,
    *,
    batch_size: int = 100_000,
) -> PunjabArtifactReport:
    """Join Punjab roll rows to Indicate transcriptions and resolve surnames.

    Args:
        roll_path: Dataverse Punjab CSV or CSV.GZ from dataset version 25.0.
        transliteration_path: Row-aligned Indicate Punjab Parquet artifact.
        output_path: Destination person-level Parquet path.
        batch_size: Rows processed per batch.

    Returns:
        Aggregate row, abstention, and transcription-status counts.

    Raises:
        BaseException: Re-raises source or output failures after removing the
            incomplete output artifact.
        ValueError: If schemas, row counts, or native row alignment differ.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least one")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    raw_frames = cast(
        "Iterator[pd.DataFrame]",
        pd.read_csv(
            roll_path,
            usecols=cast("Any", list(RAW_COLUMNS)),
            dtype="string",
            chunksize=batch_size,
            keep_default_na=False,
        ),
    )
    companion_frames = _companion_frames(transliteration_path, batch_size=batch_size)
    writer: pq.ParquetWriter | None = None
    source_row = 0
    abstention_reasons: Counter[str] = Counter()
    transliteration_statuses: Counter[str] = Counter()
    by_sex: dict[str, Counter[str]] = defaultdict(Counter)
    by_relationship: dict[str, Counter[str]] = defaultdict(Counter)
    surname_counts: Counter[str] = Counter()
    cache: dict[tuple[object, object], PunjabSurnameResult] = {}
    try:
        for raw, companion in zip_longest(raw_frames, companion_frames):
            if raw is None or companion is None:
                raise ValueError(
                    "roll and transliteration artifacts have different rows"
                )
            if len(raw) != len(companion):
                raise ValueError(
                    "roll and transliteration batch lengths differ at "
                    f"source_row {source_row}: {len(raw)} != {len(companion)}"
                )
            _validate_native_alignment(raw, companion, source_row=source_row)
            frame = _output_frame(raw, companion, source_row=source_row, cache=cache)
            table = pa.Table.from_pandas(
                frame, schema=PUNJAB_OUTPUT_SCHEMA, preserve_index=False, safe=True
            )
            if writer is None:
                writer = pq.ParquetWriter(
                    temporary, PUNJAB_OUTPUT_SCHEMA, compression="zstd"
                )
            writer.write_table(table, row_group_size=batch_size)
            source_row += len(frame)
            abstention_reasons.update(
                value for value in frame["abstention_reason"] if isinstance(value, str)
            )
            transliteration_statuses.update(frame["transliteration_status"])
            surname_counts.update(_column(frame, "surname_canonical").dropna())
            _update_strata(by_sex, _column(raw, "sex"), frame)
            _update_strata(by_relationship, _column(raw, "relationship"), frame)
    except BaseException:
        if writer is not None:
            writer.close()
        temporary.unlink(missing_ok=True)
        raise
    if writer is None:
        temporary.unlink(missing_ok=True)
        raise ValueError("Punjab source contains no rows")
    writer.close()
    temporary.replace(output_path)
    return PunjabArtifactReport(
        rows=source_row,
        abstention_reasons=abstention_reasons,
        transliteration_statuses=transliteration_statuses,
        by_sex=by_sex,
        by_relationship=by_relationship,
        top_surnames=tuple(surname_counts.most_common(25)),
    )


def write_punjab_audit(path: Path, report: PunjabArtifactReport) -> None:
    """Write the non-identifying Punjab run diagnostics as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(report.as_dict(), stream, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)


def write_punjab_summary(path: Path, report: PunjabArtifactReport) -> None:
    """Write a compact, non-identifying Punjab coverage table as CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    fields = (
        "group",
        "value",
        "rows",
        "native_resolved",
        "ascii_resolved",
        "abstained",
        "transliteration_aligned",
        "transliteration_token-count-mismatch",
        "transliteration_ineligible-latin-token",
        "transliteration_no-surname-selected",
    )
    overall = {
        "rows": report.rows,
        "native_resolved": report.rows - sum(report.abstention_reasons.values()),
        "ascii_resolved": report.transliteration_statuses.get("aligned", 0),
        "abstained": sum(report.abstention_reasons.values()),
        **{
            f"transliteration_{status}": count
            for status, count in report.transliteration_statuses.items()
        },
    }
    groups: list[tuple[str, str, Mapping[str, int]]] = [("overall", "all", overall)]
    groups.extend(("sex", key, value) for key, value in sorted(report.by_sex.items()))
    groups.extend(
        ("relationship", key, value)
        for key, value in sorted(report.by_relationship.items())
    )
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for group, value, counts in groups:
            writer.writerow(
                {
                    "group": group,
                    "value": value,
                    **{field: counts.get(field, 0) for field in fields[2:]},
                }
            )
    temporary.replace(path)
