"""Aggregate written surname tokens from Bihar ration-card rosters."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from upnaam.normalization import NORMALIZATION_REVISION
from upnaam.selection import extract_surname_candidates
from upnaam.tables import write_table

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

BIHAR_RATION_AGGREGATE_REVISION = "bihar-ration-written-surname-counts-v1"
BIHAR_RATION_MEMBER_NAME_FIELD = "सदस्य का नाम"
BIHAR_RATION_PROVENANCE = "bihar_ration_written_final_token"

BIHAR_RATION_AGGREGATE_COLUMNS = [
    "surname_source_normalized",
    "surname_raw_mode",
    "surname_raw_mode_count",
    "raw_variant_count",
    "member_count",
    "household_count",
    "surname_provenance",
    "normalization_revision",
    "aggregate_revision",
]


@dataclass(frozen=True, slots=True)
class BiharRationAggregateReport:
    """Non-identifying diagnostics for one Bihar ration roster scan."""

    source_households: int
    declared_members: int
    parsed_member_rows: int
    valid_member_rows: int
    selected_members: int
    abstained_members: int
    households_with_selected_surname: int
    distinct_surnames: int
    member_count_mismatch_households: int
    missing_declared_member_count_households: int
    malformed_json_households: int
    non_list_roster_households: int
    invalid_member_rows: int
    abstentions_by_reason: dict[str, int]
    source_scan_complete: bool
    household_limit: int | None


def _mode(raw_counts: Mapping[str, int]) -> tuple[str, int]:
    """Choose the most frequent raw value, breaking ties lexicographically."""
    return min(raw_counts.items(), key=lambda item: (-item[1], item[0]))


def aggregate_bihar_ration_rows(
    rows: Iterable[Sequence[object]],
    *,
    household_limit: int | None = None,
) -> tuple[pd.DataFrame, BiharRationAggregateReport]:
    """Aggregate surname counts from streamed Bihar household roster rows.

    Args:
        rows: Sequences containing household ID, declared member count, and
            JSON roster text.
        household_limit: Declared upstream row limit, if this is a partial scan.

    Returns:
        Grouped surname table and aggregate scan diagnostics.

    Raises:
        ValueError: If a source row does not contain exactly three values or
            ``household_limit`` is invalid.
    """
    if household_limit is not None and household_limit < 1:
        raise ValueError("household_limit must be at least one")

    member_counts: Counter[str] = Counter()
    household_counts: Counter[str] = Counter()
    raw_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    abstentions: Counter[str] = Counter()
    source_households = 0
    declared_members = 0
    parsed_member_rows = 0
    valid_member_rows = 0
    mismatch_households = 0
    missing_declared_households = 0
    malformed_json_households = 0
    non_list_roster_households = 0
    invalid_member_rows = 0
    households_with_selected_surname = 0

    for row in rows:
        if len(row) != 3:
            raise ValueError("Bihar ration rows must contain exactly three values")
        _, declared_value, roster_value = row
        source_households += 1
        if isinstance(declared_value, int) and not isinstance(declared_value, bool):
            declared_members += declared_value
        else:
            missing_declared_households += 1

        if not isinstance(roster_value, str):
            malformed_json_households += 1
            continue
        try:
            roster: Any = json.loads(roster_value)
        except (json.JSONDecodeError, UnicodeDecodeError):
            malformed_json_households += 1
            continue
        if not isinstance(roster, list):
            non_list_roster_households += 1
            continue

        parsed_member_rows += len(roster)
        if isinstance(declared_value, int) and declared_value != len(roster):
            mismatch_households += 1
        household_surnames: set[str] = set()
        for member in roster:
            if not isinstance(member, dict):
                invalid_member_rows += 1
                continue
            valid_member_rows += 1
            name = cast("Mapping[str, object]", member).get(
                BIHAR_RATION_MEMBER_NAME_FIELD
            )
            selected = extract_surname_candidates(name)
            if selected.surname is None:
                abstentions[selected.abstention_reason or "unknown"] += 1
                continue
            normalized = selected.surname.normalized
            member_counts[normalized] += 1
            raw_counts[normalized][selected.surname.raw] += 1
            household_surnames.add(normalized)
        if household_surnames:
            households_with_selected_surname += 1
            household_counts.update(household_surnames)

    records: list[dict[str, object]] = []
    for normalized, member_count in member_counts.items():
        raw_mode, raw_mode_count = _mode(raw_counts[normalized])
        records.append(
            {
                "surname_source_normalized": normalized,
                "surname_raw_mode": raw_mode,
                "surname_raw_mode_count": raw_mode_count,
                "raw_variant_count": len(raw_counts[normalized]),
                "member_count": member_count,
                "household_count": household_counts[normalized],
                "surname_provenance": BIHAR_RATION_PROVENANCE,
                "normalization_revision": NORMALIZATION_REVISION,
                "aggregate_revision": BIHAR_RATION_AGGREGATE_REVISION,
            }
        )
    records.sort(
        key=lambda item: (
            -cast("int", item["member_count"]),
            cast("str", item["surname_source_normalized"]),
        )
    )
    frame = pd.DataFrame(records, columns=BIHAR_RATION_AGGREGATE_COLUMNS)
    for column in (
        "surname_source_normalized",
        "surname_raw_mode",
        "surname_provenance",
        "normalization_revision",
        "aggregate_revision",
    ):
        frame[column] = frame[column].astype("string")
    for column in (
        "surname_raw_mode_count",
        "raw_variant_count",
        "member_count",
        "household_count",
    ):
        frame[column] = frame[column].astype("int64")

    selected_members = sum(member_counts.values())
    report = BiharRationAggregateReport(
        source_households=source_households,
        declared_members=declared_members,
        parsed_member_rows=parsed_member_rows,
        valid_member_rows=valid_member_rows,
        selected_members=selected_members,
        abstained_members=sum(abstentions.values()),
        households_with_selected_surname=households_with_selected_surname,
        distinct_surnames=len(member_counts),
        member_count_mismatch_households=mismatch_households,
        missing_declared_member_count_households=missing_declared_households,
        malformed_json_households=malformed_json_households,
        non_list_roster_households=non_list_roster_households,
        invalid_member_rows=invalid_member_rows,
        abstentions_by_reason=dict(sorted(abstentions.items())),
        source_scan_complete=household_limit is None,
        household_limit=household_limit,
    )
    return frame, report


def build_bihar_ration_surname_counts(
    parts: Sequence[Path],
    index_path: Path,
    output_path: Path,
    *,
    household_limit: int | None = None,
) -> BiharRationAggregateReport:
    """Scan compressed Bihar rosters and write grouped surname counts.

    Args:
        parts: Ordered gzip-compressed SQLite archive parts.
        index_path: Verified indexed-gzip seek index.
        output_path: Aggregate CSV or Parquet destination.
        household_limit: Optional source-row limit for a diagnostic pilot.

    Returns:
        Aggregate scan diagnostics.

    Raises:
        ValueError: If ``household_limit`` is less than one.
    """
    from upnaam.compressed_sqlite import open_gzip_sqlite

    query = "SELECT id, members_qty, sub_table FROM family_members_tables"
    parameters: tuple[int, ...] = ()
    if household_limit is not None:
        if household_limit < 1:
            raise ValueError("household_limit must be at least one")
        query = f"{query} LIMIT ?"
        parameters = (household_limit,)
    with open_gzip_sqlite(parts, index_path) as connection:
        frame, report = aggregate_bihar_ration_rows(
            connection.execute(query, parameters),
            household_limit=household_limit,
        )
    write_table(frame, output_path)
    return report


def write_bihar_ration_aggregate_audit(
    path: Path, report: BiharRationAggregateReport
) -> None:
    """Write public-safe Bihar ration aggregation diagnostics as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(asdict(report), stream, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)
