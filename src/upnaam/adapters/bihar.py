"""Bihar land-record reference labels for linked electoral names."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from upnaam.normalization import NORMALIZATION_REVISION, NameToken, normalize_name
from upnaam.selection import extract_surname_candidates

if TYPE_CHECKING:
    from pathlib import Path


BIHAR_REFERENCE_REVISION = "bihar-land-reference-v1"
BIHAR_LINKAGE_BASIS = "exact_normalized_block_full_name_relative_unique_1to1"

BIHAR_REFERENCE_SCHEMA = pa.schema(
    [
        ("link_id", pa.string()),
        ("roll_id", pa.string()),
        ("land_account_no", pa.string()),
        ("roll_name_raw", pa.string()),
        ("land_name_raw", pa.string()),
        ("roll_surname_raw", pa.string()),
        ("roll_surname_source_normalized", pa.string()),
        ("land_surname_raw", pa.string()),
        ("land_surname_source_normalized", pa.string()),
        ("reference_surname_raw", pa.string()),
        ("reference_surname_source_normalized", pa.string()),
        ("reference_label_status", pa.string()),
        ("reference_label_reason", pa.string()),
        ("reference_provenance", pa.string()),
        ("reference_position", pa.string()),
        ("relation_type", pa.string()),
        ("sex", pa.string()),
        ("full_name_normalized_agreement", pa.bool_()),
        ("linkage_basis", pa.string()),
        ("normalization_revision", pa.string()),
        ("reference_revision", pa.string()),
    ]
)


@dataclass(frozen=True, slots=True)
class BiharReferenceReport:
    """Non-identifying diagnostics for Bihar reference labels."""

    source_links: int
    accepted_labels: int
    agreement_labels: int
    land_added_labels: int
    abstained_labels: int
    excluded_conflicts: int
    full_name_normalized_agreements: int
    distinct_reference_surnames: int
    by_sex: dict[str, dict[str, int]]


def _sex_group(value: object) -> str:
    if isinstance(value, str) and value in {"female", "male"}:
        return value
    return "unknown"


def _selected_surname(
    value: object, cache: dict[str | None, NameToken | None]
) -> NameToken | None:
    key = value if isinstance(value, str) else None
    if key not in cache:
        cache[key] = extract_surname_candidates(key).surname
    return cache[key]


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Bihar reference field must be a nonempty string: {field}")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is None or cast("bool", pd.isna(cast("Any", value))):
        return None
    if not isinstance(value, str):
        raise ValueError(f"Bihar reference field must be a string or null: {field}")
    return value


def build_bihar_land_reference_labels(
    links_path: Path,
    output_path: Path,
    *,
    batch_size: int = 100_000,
) -> BiharReferenceReport:
    """Prefer official land spellings on accepted Bihar person links.

    Args:
        links_path: Standardized accepted Bihar land-link Parquet artifact.
        output_path: Restricted one-row-per-link reference-label artifact.
        batch_size: Accepted links processed per batch.

    Returns:
        Aggregate label coverage and conflict diagnostics.

    Raises:
        ValueError: If the input violates the exact one-to-one link contract.
        BaseException: After removing an incomplete temporary output.

    Notes:
        The official land record is treated as the preferred transcription.
        It contains a full name rather than an explicit surname field, so the
        final eligible token remains the declared Bihar positional rule.
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
        "edit_learning_eligible",
        "omission_eligible",
    }
    missing = required.difference(parquet.schema_arrow.names)
    if missing:
        raise ValueError(f"Bihar accepted links are missing columns: {sorted(missing)}")

    rows: list[dict[str, object]] = []
    seen_link_ids: set[str] = set()
    seen_roll_ids: set[str] = set()
    seen_land_ids: set[str] = set()
    statuses: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    by_sex: defaultdict[str, Counter[str]] = defaultdict(Counter)
    reference_surnames: set[str] = set()
    full_name_agreements = 0
    cache: dict[str | None, NameToken | None] = {}
    columns = sorted(required)
    for batch in parquet.iter_batches(batch_size=batch_size, columns=columns):
        frame = batch.to_pandas()
        for item in frame.to_dict(orient="records"):
            if item["source"] != "bihar_land":
                raise ValueError("Bihar reference input contains another source")
            if item["link_tier"] != "exact_name_and_relative":
                raise ValueError("Bihar reference input contains another link tier")
            if (
                item["name_exact_upstream"] is not True
                or item["edit_learning_eligible"] is not False
                or item["omission_eligible"] is not False
            ):
                raise ValueError(
                    "Bihar reference input violates linkage eligibility flags"
                )

            link_id = _require_string(item["link_id"], "link_id")
            roll_id = _require_string(item["roll_id"], "roll_id")
            land_id = _require_string(item["external_id"], "external_id")
            if (
                link_id in seen_link_ids
                or roll_id in seen_roll_ids
                or land_id in seen_land_ids
            ):
                raise ValueError("Bihar reference links must be one-to-one")
            seen_link_ids.add(link_id)
            seen_roll_ids.add(roll_id)
            seen_land_ids.add(land_id)

            roll_name = _require_string(item["roll_name_raw"], "roll_name_raw")
            land_name = _require_string(item["external_name_raw"], "external_name_raw")
            roll_surname = _selected_surname(roll_name, cache)
            land_surname = _selected_surname(land_name, cache)
            full_name_agreement = normalize_name(roll_name) == normalize_name(land_name)
            full_name_agreements += int(full_name_agreement)

            if land_surname is None:
                status = "abstained"
                reason = "land_surname_unresolved"
                reference = None
            elif roll_surname is None:
                status = "accepted"
                reason = "land_record_adds_reference_surname"
                reference = land_surname
            elif roll_surname.normalized != land_surname.normalized:
                status = "excluded"
                reason = "land_roll_position_conflict"
                reference = None
            else:
                status = "accepted"
                reason = "land_and_roll_surname_agree"
                reference = land_surname

            statuses[status] += 1
            reasons[reason] += 1
            relation_type = _optional_string(item["relation_type"], "relation_type")
            sex_value = _optional_string(item["sex"], "sex")
            sex = _sex_group(sex_value)
            by_sex[sex][status] += 1
            if reference is not None:
                reference_surnames.add(reference.normalized)
            rows.append(
                {
                    "link_id": link_id,
                    "roll_id": roll_id,
                    "land_account_no": land_id,
                    "roll_name_raw": roll_name,
                    "land_name_raw": land_name,
                    "roll_surname_raw": (
                        roll_surname.raw if roll_surname is not None else None
                    ),
                    "roll_surname_source_normalized": (
                        roll_surname.normalized if roll_surname is not None else None
                    ),
                    "land_surname_raw": (
                        land_surname.raw if land_surname is not None else None
                    ),
                    "land_surname_source_normalized": (
                        land_surname.normalized if land_surname is not None else None
                    ),
                    "reference_surname_raw": (
                        reference.raw if reference is not None else None
                    ),
                    "reference_surname_source_normalized": (
                        reference.normalized if reference is not None else None
                    ),
                    "reference_label_status": status,
                    "reference_label_reason": reason,
                    "reference_provenance": (
                        "land_record" if reference is not None else None
                    ),
                    "reference_position": "last" if reference is not None else None,
                    "relation_type": relation_type,
                    "sex": sex_value,
                    "full_name_normalized_agreement": full_name_agreement,
                    "linkage_basis": BIHAR_LINKAGE_BASIS,
                    "normalization_revision": NORMALIZATION_REVISION,
                    "reference_revision": BIHAR_REFERENCE_REVISION,
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    try:
        pq.write_table(
            pa.Table.from_pylist(rows, schema=BIHAR_REFERENCE_SCHEMA),
            temporary,
            compression="zstd",
        )
        temporary.replace(output_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return BiharReferenceReport(
        source_links=len(rows),
        accepted_labels=statuses["accepted"],
        agreement_labels=reasons["land_and_roll_surname_agree"],
        land_added_labels=reasons["land_record_adds_reference_surname"],
        abstained_labels=statuses["abstained"],
        excluded_conflicts=statuses["excluded"],
        full_name_normalized_agreements=full_name_agreements,
        distinct_reference_surnames=len(reference_surnames),
        by_sex={
            sex: dict(sorted(counts.items())) for sex, counts in sorted(by_sex.items())
        },
    )


def write_bihar_reference_audit(path: Path, report: BiharReferenceReport) -> None:
    """Write aggregate Bihar reference-label diagnostics as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(asdict(report), stream, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)


def write_bihar_reference_summary(path: Path, report: BiharReferenceReport) -> None:
    """Write public-safe aggregate Bihar reference-label counts as CSV."""
    rows: list[dict[str, object]] = [
        {
            "group": "overall",
            "value": "all",
            "rows": report.source_links,
            "accepted": report.accepted_labels,
            "abstained": report.abstained_labels,
            "excluded": report.excluded_conflicts,
        }
    ]
    for sex, counts in sorted(report.by_sex.items()):
        rows.append(
            {
                "group": "sex",
                "value": sex,
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
