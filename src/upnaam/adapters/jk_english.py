"""Corroborated name tokens from the audited historical J&K English inventory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from upnaam.adapters.electors import ElectorSource
from upnaam.adapters.jk_inventory import InventoryProfile, resolve_inventory

SOURCE = ElectorSource(
    state="jammu_kashmir_ladakh",
    source_revision="jk-english-2018",
    resolver_revision="jk-english-elector-resolver-v1",
    name_source_column="elector_name_source",
    relation_source_column="relative_name_source",
    zero_house_is_missing=True,
    preserve_house_separators=True,
    reject_evidence_conflicts=True,
    exact_spelling=True,
    confidence_diagnostic=False,
)
RELATIONSHIPS = {
    "Father's Name": "father",
    "Mother's Name": "mother",
    "Husband's Name": "husband",
}


def _accepted(value: object, issue: object) -> str | None:
    if (
        isinstance(value, str)
        and value.strip()
        and issue is None
        and all(32 <= ord(char) < 127 for char in value)
    ):
        return value
    return None


PROFILE = InventoryProfile(
    source=SOURCE,
    language="English",
    parser_filename="jk_english_rows.py",
    filename_pattern=r"EACA(0(?:47|48|49|50))PS([0-9]{4})\.pdf",
    relationships=RELATIONSHIPS,
    accept_name=_accepted,
    accept_house=_accepted,
    description=(
        "Active assembly rows only; raw candidates retain source text. "
        "Elector and relative evidence require accepted ASCII source names. "
        "Relationships map only father, mother and husband; "
        "house zero is missing evidence."
    ),
    limitations=(
        "Historical AC047-AC050 only, now Ladakh; not full-state coverage.",
        "Source count discrepancies and missing pages remain unresolved.",
        "Corroborated written tokens are not verified hereditary surnames.",
        "Uncorroborated or conflicting evidence abstains; confidence is null.",
        "Relative-only candidates remain separate from recorded selections.",
        "No transliteration, spelling merge, lookup or model promotion.",
    ),
    module_path=Path(__file__),
)


def resolve_jk_english(
    inventory: Path, source_audit: Path, output_dir: Path
) -> dict[str, Any]:
    """Validate the English source and preserve every active assembly row.

    Args:
        inventory: Reconciled inventory Parquet.
        source_audit: Parser audit with source hashes and per-part counts.
        output_dir: New directory for the restricted output artifacts.

    Returns:
        Source checks, exclusions, evidence counts and artifact hashes.
    """
    return resolve_inventory(inventory, source_audit, output_dir, PROFILE)
