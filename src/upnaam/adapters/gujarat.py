"""Surname artifact construction for the recovered Gujarat 2017 rolls."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

from upnaam.normalization import (
    NORMALIZATION_REVISION,
    normalize_latin_token,
)
from upnaam.schema import CANONICALIZATION_REVISION, CanonicalizationStatus
from upnaam.selection import extract_surname_candidates

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

GUJARAT_RESOLVER_REVISION = "gujarat-elector-resolver-v1"
GUJARAT_SOURCE_REVISION = "og47iv-gujarat-2017-recovered"

GUJARAT_OUTPUT_SCHEMA = pa.schema(
    [
        ("record_id", pa.string()),
        ("source_filename", pa.string()),
        ("assembly_constituency", pa.int16()),
        ("part_number", pa.int16()),
        ("source_page", pa.int16()),
        ("serial_number", pa.int32()),
        ("epic_id", pa.string()),
        ("house_number", pa.string()),
        ("relationship", pa.string()),
        ("name_source_raw", pa.string()),
        ("relative_name_source_raw", pa.string()),
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
        ("surname_evidence", pa.string()),
        ("abstained", pa.bool_()),
        ("abstention_reason", pa.string()),
        ("transliteration_status", pa.string()),
        ("normalization_revision", pa.string()),
        ("resolver_revision", pa.string()),
        ("transliteration_revision", pa.string()),
    ]
)

REQUIRED_COLUMNS = frozenset(
    {
        "record_id",
        "source_filename",
        "assembly_constituency",
        "part_number",
        "source_page",
        "serial_number",
        "epic_id",
        "house_number",
        "relationship",
        "elector_name_native",
        "relative_name_native",
    }
)


@dataclass(frozen=True, slots=True)
class GujaratSurnameResult:
    """One native first-position decision and optional Latin mapping."""

    surname_raw: str | None
    surname_source_normalized: str | None
    surname_latin_raw: str | None
    surname_latin_normalized: str | None
    abstained: bool
    abstention_reason: str | None
    transliteration_status: str


@dataclass(frozen=True, slots=True)
class GujaratArtifactReport:
    """Aggregate checks for a Gujarat elector artifact."""

    rows: int
    selected_native: int
    mapped_latin: int
    abstained: int
    abstention_reasons: Mapping[str, int]
    transliteration_statuses: Mapping[str, int]
    top_surnames: tuple[tuple[str, int], ...]
    resolver_revision: str
    transliteration_revision: str

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serializable report."""
        payload = asdict(self)
        payload["abstention_reasons"] = dict(sorted(self.abstention_reasons.items()))
        payload["transliteration_statuses"] = dict(
            sorted(self.transliteration_statuses.items())
        )
        payload["top_surnames"] = [
            {"surname": surname, "rows": rows} for surname, rows in self.top_surnames
        ]
        return payload


def resolve_gujarat_name(
    native_name: object,
    romanize_token: Callable[[str], str | None],
) -> GujaratSurnameResult:
    """Select the first eligible token and map that exact token when possible.

    Gujarat's source names are printed surname-first. A one-token name remains
    ambiguous and abstains under the shared positional-candidate contract.

    Args:
        native_name: Source-script elector name.
        romanize_token: Local, deterministic native-token lookup.

    Returns:
        Native selection, optional Latin mapping, and explicit status.
    """
    candidates = extract_surname_candidates(native_name)
    if candidates.abstained or candidates.first_candidate is None:
        return GujaratSurnameResult(
            surname_raw=None,
            surname_source_normalized=None,
            surname_latin_raw=None,
            surname_latin_normalized=None,
            abstained=True,
            abstention_reason=candidates.abstention_reason,
            transliteration_status="no-surname-selected",
        )
    selected = candidates.first_candidate
    latin_raw = romanize_token(selected.raw)
    if latin_raw is None:
        return GujaratSurnameResult(
            selected.raw,
            selected.normalized,
            None,
            None,
            False,
            None,
            "lookup-miss",
        )
    latin_raw = latin_raw.strip()
    latin_normalized = normalize_latin_token(latin_raw)
    if not re.fullmatch(r"[A-Za-z]+", latin_raw) or latin_normalized is None:
        return GujaratSurnameResult(
            selected.raw,
            selected.normalized,
            None,
            None,
            False,
            None,
            "invalid-latin-token",
        )
    return GujaratSurnameResult(
        selected.raw,
        selected.normalized,
        latin_raw,
        latin_normalized,
        False,
        None,
        "mapped",
    )


def _output_row(
    source: dict[str, object],
    result: GujaratSurnameResult,
    *,
    transliteration_revision: str,
) -> dict[str, object]:
    latin = result.surname_latin_normalized
    return {
        "record_id": source["record_id"],
        "source_filename": source["source_filename"],
        "assembly_constituency": source["assembly_constituency"],
        "part_number": source["part_number"],
        "source_page": source["source_page"],
        "serial_number": source["serial_number"],
        "epic_id": source["epic_id"],
        "house_number": source["house_number"],
        "relationship": source["relationship"],
        "name_source_raw": source["elector_name_native"],
        "relative_name_source_raw": source["relative_name_native"],
        "surname_raw": result.surname_raw,
        "surname_source_normalized": result.surname_source_normalized,
        "surname_latin_raw": result.surname_latin_raw,
        "surname_latin_normalized": latin,
        "surname_canonical": latin,
        "canonicalization_status": (
            CanonicalizationStatus.IDENTITY_UNMAPPED.value
            if latin
            else CanonicalizationStatus.NOT_APPLICABLE.value
        ),
        "canonicalization_reason": (
            "no_reconciliation_decision"
            if latin
            else "surname_not_selected"
            if result.abstained
            else "latin_form_unavailable"
        ),
        "canonicalization_provenance": None,
        "canonicalization_revision": CANONICALIZATION_REVISION,
        "surname_position": "first" if result.surname_raw else None,
        "surname_provenance": "written_first_token" if result.surname_raw else None,
        "surname_evidence": "position" if result.surname_raw else None,
        "abstained": result.abstained,
        "abstention_reason": result.abstention_reason,
        "transliteration_status": result.transliteration_status,
        "normalization_revision": NORMALIZATION_REVISION,
        "resolver_revision": GUJARAT_RESOLVER_REVISION,
        "transliteration_revision": transliteration_revision,
    }


def build_gujarat_elector_artifact(
    records_path: Path,
    output_path: Path,
    *,
    romanize_token: Callable[[str], str | None],
    transliteration_revision: str,
    batch_size: int = 100_000,
) -> GujaratArtifactReport:
    """Resolve a recovered Gujarat roll into the standard surname fields.

    Args:
        records_path: Recovered Gujarat elector Parquet.
        output_path: Destination person-level surname Parquet.
        romanize_token: Local native-token lookup.
        transliteration_revision: Immutable identifier for that lookup.
        batch_size: Source rows read per batch.

    Returns:
        Aggregate selection and mapping counts.

    Raises:
        ValueError: The input schema, revision, or batch size is invalid.
        BaseException: Re-raises processing failures after removing partial output.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least one")
    if not transliteration_revision.strip():
        raise ValueError("transliteration_revision must be nonempty")
    source = pq.ParquetFile(records_path)
    missing = REQUIRED_COLUMNS.difference(source.schema_arrow.names)
    if missing:
        raise ValueError(f"Gujarat input is missing columns: {sorted(missing)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    writer = pq.ParquetWriter(temporary, GUJARAT_OUTPUT_SCHEMA, compression="zstd")
    rows = mapped = selected = 0
    statuses: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    surnames: Counter[str] = Counter()
    try:
        for batch in source.iter_batches(
            batch_size=batch_size, columns=sorted(REQUIRED_COLUMNS)
        ):
            output = []
            for row in batch.to_pylist():
                result = resolve_gujarat_name(
                    row["elector_name_native"], romanize_token
                )
                output.append(
                    _output_row(
                        row,
                        result,
                        transliteration_revision=transliteration_revision,
                    )
                )
                rows += 1
                selected += not result.abstained
                mapped += result.surname_latin_normalized is not None
                statuses[result.transliteration_status] += 1
                if result.abstention_reason:
                    reasons[result.abstention_reason] += 1
                if result.surname_latin_normalized:
                    surnames[result.surname_latin_normalized] += 1
            writer.write_table(
                pa.Table.from_pylist(output, schema=GUJARAT_OUTPUT_SCHEMA)
            )
    except BaseException:
        writer.close()
        temporary.unlink(missing_ok=True)
        raise
    writer.close()
    temporary.replace(output_path)
    return GujaratArtifactReport(
        rows=rows,
        selected_native=selected,
        mapped_latin=mapped,
        abstained=rows - selected,
        abstention_reasons=dict(reasons),
        transliteration_statuses=dict(statuses),
        top_surnames=tuple(surnames.most_common(20)),
        resolver_revision=GUJARAT_RESOLVER_REVISION,
        transliteration_revision=transliteration_revision,
    )


def write_gujarat_audit(path: Path, report: GujaratArtifactReport) -> None:
    """Write the aggregate Gujarat audit as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_json(), indent=2, sort_keys=True) + "\n")
