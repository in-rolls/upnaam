"""Rajasthan ration-card reference labels for linked electoral names."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from upnaam.normalization import NORMALIZATION_REVISION, NameToken
from upnaam.selection import extract_surname_candidates

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


RAJASTHAN_REFERENCE_REVISION = "rajasthan-ration-reference-v1"
RAJASTHAN_REFERENCE_STANDARD = "provisional_gold"
RAJASTHAN_LINKAGE_BASIS = "milaan_raj_t1_t2_member_corroborated_person_link"

RAJASTHAN_REFERENCE_SCHEMA = pa.schema(
    [
        ("reference_row_id", pa.string()),
        ("source_link_id", pa.string()),
        ("roll_id", pa.string()),
        ("ration_member_id", pa.string()),
        ("roll_name_raw", pa.string()),
        ("ration_name_raw", pa.string()),
        ("roll_surname_raw", pa.string()),
        ("roll_surname_source_normalized", pa.string()),
        ("ration_surname_raw", pa.string()),
        ("ration_surname_source_normalized", pa.string()),
        ("reference_surname_raw", pa.string()),
        ("reference_surname_source_normalized", pa.string()),
        ("reference_label_status", pa.string()),
        ("reference_label_reason", pa.string()),
        ("reference_provenance", pa.string()),
        ("reference_standard", pa.string()),
        ("reference_position", pa.string()),
        ("link_tier", pa.string()),
        ("relation_type", pa.string()),
        ("sex", pa.string()),
        ("sex_group", pa.string()),
        ("name_exact_upstream", pa.bool_()),
        ("selected_surname_normalized_agreement", pa.bool_()),
        ("ration_member_link_count", pa.int64()),
        ("linkage_basis", pa.string()),
        ("normalization_revision", pa.string()),
        ("reference_revision", pa.string()),
    ]
)


@dataclass(frozen=True, slots=True)
class RajasthanReferenceReport:
    """Non-identifying diagnostics for Rajasthan reference labels."""

    source_links: int
    unique_ration_members: int
    duplicated_ration_members: int
    accepted_labels: int
    abstained_labels: int
    excluded_nonunique_links: int
    surname_agreements: int
    surname_conflicts: int
    ration_added_labels: int
    distinct_reference_surnames: int
    by_tier: dict[str, dict[str, int]]
    by_sex: dict[str, dict[str, int]]


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Rajasthan reference field must be nonempty: {field}")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is None or cast("bool", pd.isna(cast("Any", value))):
        return None
    if not isinstance(value, str):
        raise ValueError(f"Rajasthan reference field must be a string or null: {field}")
    return value


def _require_bool(value: object, field: str) -> bool:
    if value is True or value is False:
        return bool(value)
    raise ValueError(f"Rajasthan reference field must be boolean: {field}")


def _sex_group(value: str | None) -> str:
    if value == "f":
        return "female"
    if value == "m":
        return "male"
    return "unknown"


def _selected_surname(
    value: str, cache: dict[str, NameToken | None]
) -> NameToken | None:
    if value not in cache:
        cache[value] = extract_surname_candidates(value).surname
    return cache[value]


def _validate_identity_columns(
    parquet: pq.ParquetFile,
    *,
    batch_size: int,
) -> tuple[Counter[str], int]:
    member_counts: Counter[str] = Counter()
    seen_roll_ids: set[str] = set()
    source_links = 0
    columns = ["source", "link_tier", "link_id", "roll_id", "external_id"]
    for batch in parquet.iter_batches(batch_size=batch_size, columns=columns):
        for source, tier, link_id, roll_id, member_id in batch.to_pandas().itertuples(
            index=False, name=None
        ):
            if source != "rajasthan_ration":
                raise ValueError("Rajasthan reference input contains another source")
            if tier not in {"T1", "T2"}:
                raise ValueError("Rajasthan reference input contains another link tier")
            _require_string(link_id, "link_id")
            roll_key = _require_string(roll_id, "roll_id")
            member_key = _require_string(member_id, "external_id")
            if roll_key in seen_roll_ids:
                raise ValueError("Rajasthan reference roll IDs must be unique")
            seen_roll_ids.add(roll_key)
            member_counts[member_key] += 1
            source_links += 1
    return member_counts, source_links


def _reference_row(
    item: Mapping[str, object],
    *,
    member_link_count: int,
    cache: dict[str, NameToken | None],
) -> tuple[dict[str, object], str, str, bool, bool, bool, str | None]:
    source_link_id = _require_string(item["link_id"], "link_id")
    roll_id = _require_string(item["roll_id"], "roll_id")
    member_id = _require_string(item["external_id"], "external_id")
    roll_name = _require_string(item["roll_name_raw"], "roll_name_raw")
    ration_name = _require_string(item["external_name_raw"], "external_name_raw")
    tier = _require_string(item["link_tier"], "link_tier")
    relation_type = _optional_string(item["relation_type"], "relation_type")
    sex = _optional_string(item["sex"], "sex")
    sex_group = _sex_group(sex)
    name_exact = _require_bool(item["name_exact_upstream"], "name_exact_upstream")
    roll_surname = _selected_surname(roll_name, cache)
    ration_surname = _selected_surname(ration_name, cache)

    agreement = (
        roll_surname.normalized == ration_surname.normalized
        if roll_surname is not None and ration_surname is not None
        else None
    )
    if member_link_count > 1:
        status = "excluded"
        reason = "nonunique_ration_member_link"
        reference = None
    elif ration_surname is None:
        status = "abstained"
        reason = "ration_surname_unresolved"
        reference = None
    else:
        status = "accepted"
        reason = "ration_final_token_selected"
        reference = ration_surname

    accepted = status == "accepted"
    surname_agreement = accepted and agreement is True
    surname_conflict = accepted and agreement is False
    ration_added = accepted and roll_surname is None
    row = {
        "reference_row_id": f"rajasthan-ration-reference:{roll_id}",
        "source_link_id": source_link_id,
        "roll_id": roll_id,
        "ration_member_id": member_id,
        "roll_name_raw": roll_name,
        "ration_name_raw": ration_name,
        "roll_surname_raw": roll_surname.raw if roll_surname is not None else None,
        "roll_surname_source_normalized": (
            roll_surname.normalized if roll_surname is not None else None
        ),
        "ration_surname_raw": ration_surname.raw
        if ration_surname is not None
        else None,
        "ration_surname_source_normalized": (
            ration_surname.normalized if ration_surname is not None else None
        ),
        "reference_surname_raw": reference.raw if reference is not None else None,
        "reference_surname_source_normalized": (
            reference.normalized if reference is not None else None
        ),
        "reference_label_status": status,
        "reference_label_reason": reason,
        "reference_provenance": "ration_card" if reference is not None else None,
        "reference_standard": RAJASTHAN_REFERENCE_STANDARD,
        "reference_position": "last" if reference is not None else None,
        "link_tier": tier,
        "relation_type": relation_type,
        "sex": sex,
        "sex_group": sex_group,
        "name_exact_upstream": name_exact,
        "selected_surname_normalized_agreement": agreement,
        "ration_member_link_count": member_link_count,
        "linkage_basis": RAJASTHAN_LINKAGE_BASIS,
        "normalization_revision": NORMALIZATION_REVISION,
        "reference_revision": RAJASTHAN_REFERENCE_REVISION,
    }
    return (
        row,
        status,
        tier,
        surname_agreement,
        surname_conflict,
        ration_added,
        reference.normalized if reference is not None else None,
    )


def build_rajasthan_ration_reference_labels(
    links_path: Path,
    output_path: Path,
    *,
    batch_size: int = 100_000,
) -> RajasthanReferenceReport:
    """Build provisional-gold Rajasthan labels from accepted ration links.

    Args:
        links_path: Standardized accepted Rajasthan T1/T2 person-link artifact.
        output_path: Restricted one-row-per-elector reference-label Parquet.
        batch_size: Accepted links processed per batch.

    Returns:
        Aggregate coverage, agreement, and duplicate-link diagnostics.

    Raises:
        ValueError: If the source, tier, types, or elector keys violate contract.
        BaseException: After removing an incomplete temporary output.

    Notes:
        The ration transcription is treated as provisional gold by assumption.
        The selected surname remains the declared final eligible token rather
        than an explicit surname field. A ration member linked to multiple
        electors is excluded because the source does not identify which is true.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least one")
    parquet = pq.ParquetFile(links_path)
    required = {
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
    missing = required.difference(parquet.schema_arrow.names)
    if missing:
        raise ValueError(
            f"Rajasthan accepted links are missing columns: {sorted(missing)}"
        )

    member_counts, source_links = _validate_identity_columns(
        parquet, batch_size=batch_size
    )
    statuses: Counter[str] = Counter()
    by_tier: defaultdict[str, Counter[str]] = defaultdict(Counter)
    by_sex: defaultdict[str, Counter[str]] = defaultdict(Counter)
    surname_agreements = 0
    surname_conflicts = 0
    ration_added_labels = 0
    reference_surnames: set[str] = set()
    cache: dict[str, NameToken | None] = {}
    columns = sorted(required)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    writer: pq.ParquetWriter | None = None
    try:
        writer = pq.ParquetWriter(
            temporary, RAJASTHAN_REFERENCE_SCHEMA, compression="zstd"
        )
        for batch in parquet.iter_batches(batch_size=batch_size, columns=columns):
            rows: list[dict[str, object]] = []
            for item in batch.to_pandas().to_dict(orient="records"):
                member_id = _require_string(item["external_id"], "external_id")
                (
                    row,
                    status,
                    tier,
                    agreement,
                    conflict,
                    ration_added,
                    reference_surname,
                ) = _reference_row(
                    item,
                    member_link_count=member_counts[member_id],
                    cache=cache,
                )
                rows.append(row)
                statuses[status] += 1
                by_tier[tier][status] += 1
                by_sex[cast("str", row["sex_group"])][status] += 1
                surname_agreements += int(agreement)
                surname_conflicts += int(conflict)
                ration_added_labels += int(ration_added)
                if reference_surname is not None:
                    reference_surnames.add(reference_surname)
            if rows:
                writer.write_table(
                    pa.Table.from_pylist(rows, schema=RAJASTHAN_REFERENCE_SCHEMA)
                )
        writer.close()
        writer = None
        temporary.replace(output_path)
    except BaseException:
        if writer is not None:
            writer.close()
        temporary.unlink(missing_ok=True)
        raise

    return RajasthanReferenceReport(
        source_links=source_links,
        unique_ration_members=len(member_counts),
        duplicated_ration_members=sum(count > 1 for count in member_counts.values()),
        accepted_labels=statuses["accepted"],
        abstained_labels=statuses["abstained"],
        excluded_nonunique_links=statuses["excluded"],
        surname_agreements=surname_agreements,
        surname_conflicts=surname_conflicts,
        ration_added_labels=ration_added_labels,
        distinct_reference_surnames=len(reference_surnames),
        by_tier={
            tier: dict(sorted(counts.items()))
            for tier, counts in sorted(by_tier.items())
        },
        by_sex={
            sex: dict(sorted(counts.items())) for sex, counts in sorted(by_sex.items())
        },
    )


def write_rajasthan_reference_audit(
    path: Path, report: RajasthanReferenceReport
) -> None:
    """Write aggregate Rajasthan reference-label diagnostics as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(asdict(report), stream, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)


def write_rajasthan_reference_summary(
    path: Path, report: RajasthanReferenceReport
) -> None:
    """Write public-safe Rajasthan reference-label counts as CSV."""
    rows: list[dict[str, object]] = [
        {
            "group": "overall",
            "value": "all",
            "rows": report.source_links,
            "accepted": report.accepted_labels,
            "abstained": report.abstained_labels,
            "excluded": report.excluded_nonunique_links,
        }
    ]
    for group, values in (("tier", report.by_tier), ("sex", report.by_sex)):
        for value, counts in sorted(values.items()):
            rows.append(
                {
                    "group": group,
                    "value": value,
                    "rows": sum(counts.values()),
                    "accepted": counts.get("accepted", 0),
                    "abstained": counts.get("abstained", 0),
                    "excluded": counts.get("excluded", 0),
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    pd.DataFrame(rows).to_csv(temporary, index=False)
    temporary.replace(path)
