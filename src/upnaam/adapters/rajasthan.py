"""Rajasthan accepted-link adapter for anchored surname evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
from rapidfuzz.distance import Levenshtein

from upnaam.selection import extract_surname_candidates

if TYPE_CHECKING:
    from pathlib import Path

    from upnaam.normalization import NameToken


RAJASTHAN_RECONCILIATION_CONTEXT = (
    "state=rajasthan|source=electoral_roll|script=devanagari|position=last"
)
RAJASTHAN_EVIDENCE_REVISION = "rajasthan-ration-surname-evidence-v1"

RAJASTHAN_EVIDENCE_SCHEMA = pa.schema(
    [
        ("observed_form", pa.string()),
        ("context", pa.string()),
        ("canonical_id", pa.string()),
        ("canonical_label", pa.string()),
        ("support", pa.int64()),
        ("similarity", pa.float64()),
        ("source", pa.string()),
        ("evidence_tier", pa.string()),
        ("linkage_basis", pa.string()),
        ("evidence_revision", pa.string()),
    ]
)


@dataclass(frozen=True, slots=True)
class RajasthanEvidenceReport:
    """Non-identifying diagnostics for the Rajasthan evidence build."""

    accepted_links: int
    surname_pairs: int
    exact_surname_pairs: int
    distinct_observed_forms: int
    distinct_anchor_labels: int
    directed_evidence_rows: int
    skipped_by_reason: dict[str, int]


def _anchor_id(label: str) -> str:
    payload = f"rajasthan_ration|devanagari|{label}".encode()
    return f"rajasthan-ration-devanagari:{hashlib.sha256(payload).hexdigest()}"


def _selected_surname(
    value: object, cache: dict[object, NameToken | None]
) -> NameToken | None:
    key = value if isinstance(value, str) else None
    if key not in cache:
        result = extract_surname_candidates(key)
        cache[key] = result.surname
    return cache[key]


def build_rajasthan_surname_evidence(
    links_path: Path,
    output_path: Path,
    *,
    batch_size: int = 100_000,
) -> RajasthanEvidenceReport:
    """Aggregate surname-only evidence from accepted Rajasthan T1/T2 links.

    Args:
        links_path: Unified accepted-link Parquet artifact.
        output_path: Restricted directed evidence Parquet artifact.
        batch_size: Accepted links processed per batch.

    Returns:
        Aggregate coverage and evidence counts.

    Raises:
        ValueError: If inputs violate the accepted-link contract.
        BaseException: After removing an incomplete temporary output.

    Notes:
        The ration-side final eligible token is a provisional anchor, not gold
        truth. Upstream linkage required equality of the complete name
        skeleton, so this artifact is developmental and cannot evaluate broad
        out-of-skeleton variant recovery.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least one")
    parquet = pq.ParquetFile(links_path)
    required = {
        "source",
        "link_tier",
        "roll_name_raw",
        "external_name_raw",
    }
    missing = required.difference(parquet.schema_arrow.names)
    if missing:
        raise ValueError(f"accepted links are missing columns: {sorted(missing)}")

    counts: Counter[tuple[str, str, str]] = Counter()
    skipped: Counter[str] = Counter()
    accepted_links = 0
    surname_pairs = 0
    exact_surname_pairs = 0
    cache: dict[object, NameToken | None] = {}
    columns = ["source", "link_tier", "roll_name_raw", "external_name_raw"]
    for batch in parquet.iter_batches(batch_size=batch_size, columns=columns):
        frame = batch.to_pandas()
        for source, tier, roll_name, external_name in frame.itertuples(
            index=False, name=None
        ):
            if source != "rajasthan_ration":
                continue
            if tier not in {"T1", "T2"}:
                raise ValueError(f"unsupported Rajasthan link tier: {tier}")
            accepted_links += 1
            observed = _selected_surname(roll_name, cache)
            anchor = _selected_surname(external_name, cache)
            if observed is None:
                skipped["roll_surname_unresolved"] += 1
                continue
            if anchor is None:
                skipped["ration_surname_unresolved"] += 1
                continue
            surname_pairs += 1
            exact_surname_pairs += int(observed.normalized == anchor.normalized)
            counts[(observed.normalized, anchor.normalized, str(tier))] += 1

    rows = []
    observed_forms: set[str] = set()
    anchor_labels: set[str] = set()
    for (observed, label, tier), support in sorted(counts.items()):
        observed_forms.add(observed)
        anchor_labels.add(label)
        rows.append(
            {
                "observed_form": observed,
                "context": RAJASTHAN_RECONCILIATION_CONTEXT,
                "canonical_id": _anchor_id(label),
                "canonical_label": label,
                "support": support,
                "similarity": 1 - Levenshtein.normalized_distance(observed, label),
                "source": f"rajasthan_ration:{tier}",
                "evidence_tier": "linked_record",
                "linkage_basis": "milaan_raj_complete_name_skeleton_equality",
                "evidence_revision": RAJASTHAN_EVIDENCE_REVISION,
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    try:
        pq.write_table(
            pa.Table.from_pylist(rows, schema=RAJASTHAN_EVIDENCE_SCHEMA),
            temporary,
            compression="zstd",
        )
        temporary.replace(output_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return RajasthanEvidenceReport(
        accepted_links=accepted_links,
        surname_pairs=surname_pairs,
        exact_surname_pairs=exact_surname_pairs,
        distinct_observed_forms=len(observed_forms),
        distinct_anchor_labels=len(anchor_labels),
        directed_evidence_rows=len(rows),
        skipped_by_reason=dict(sorted(skipped.items())),
    )


def write_rajasthan_evidence_audit(path: Path, report: RajasthanEvidenceReport) -> None:
    """Write aggregate Rajasthan evidence diagnostics as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(asdict(report), stream, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)
