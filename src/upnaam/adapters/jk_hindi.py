"""Native-script corroboration from the audited historical J&K Hindi inventory."""

from __future__ import annotations

import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any

from upnaam.adapters.devanagari import devanagari_character, devanagari_tokens
from upnaam.adapters.electors import ElectorSource
from upnaam.adapters.jk_inventory import (
    InventoryProfile,
    load_romanization_map,
    resolve_inventory,
)

SOURCE = ElectorSource(
    state="jammu_kashmir_ladakh",
    source_revision="jk-hindi-2018",
    resolver_revision="jk-hindi-elector-resolver-v3",
    name_source_column="elector_name_source",
    relation_source_column="relative_name_source",
    evidence_script="devanagari",
    record_key_column="entry_event_key",
    zero_house_is_missing=True,
    preserve_house_separators=True,
    reject_evidence_conflicts=True,
    exact_spelling=True,
    confidence_diagnostic=False,
)


def _accepted_house(value: object, issue: object) -> str | None:
    if (
        isinstance(value, str)
        and value.strip()
        and issue is None
        and "\ufffd" not in value
        and all(not unicodedata.category(char).startswith("C") for char in value)
    ):
        return value
    return None


def _accepted_name(value: object, issue: object) -> str | None:
    if not isinstance(value, str) or issue is not None or not value.strip():
        return None
    if not any(devanagari_character(char) and char.isalpha() for char in value):
        return None
    if all(
        devanagari_character(char) or char in " .-'\u2019\u200c\u200d" for char in value
    ):
        return value
    return None


LIMITATIONS = (
    "Historical Hindi AC057-AC080 only; not full-state or current coverage.",
    "Source count discrepancies and missing pages remain unresolved.",
    "Corroborated written tokens are not verified hereditary surnames.",
    "Shared given names can supply corroboration; surname accuracy is unmeasured.",
    "Uncorroborated or conflicting evidence abstains; confidence is null.",
    "Relative-only candidates remain separate from recorded selections.",
)

PROFILE = InventoryProfile(
    source=SOURCE,
    language="Hindi",
    parser_filename="jk_hindi_rows.py",
    filename_pattern=r"HACA(0(?:5[7-9]|[67][0-9]|80))PS([0-9]{4})\.pdf",
    relationships={"पिता": "father", "पति": "husband"},
    accept_name=_accepted_name,
    accept_house=_accepted_house,
    description=(
        "Active assembly rows only, including missing names. Accepted Devanagari "
        "names supply exact native evidence; पिता maps to father and पति to husband. "
        "Source candidates remain raw. "
        "Zero house numbers supply no household evidence. "
        "Latin and canonical surname fields are null; no transliteration is inferred."
    ),
    limitations=(
        *LIMITATIONS,
        "No transliteration, spelling merge, lookup or model promotion.",
    ),
    module_path=Path(__file__),
)


def resolve_jk_hindi(
    inventory: Path,
    source_audit: Path,
    output_dir: Path,
    *,
    romanization_map: Path | None = None,
) -> dict[str, Any]:
    """Validate the Hindi source and preserve every active assembly row.

    Args:
        inventory: Reconciled inventory Parquet.
        source_audit: Parser audit with source hashes and per-part counts.
        output_dir: New directory for the restricted output artifacts.
        romanization_map: Optional JSON object mapping eligible native tokens to
            single ASCII Latin tokens. Applied after native selection only.

    Returns:
        Source checks, exclusions, native evidence counts and artifact hashes.
    """
    if romanization_map is None:
        return resolve_inventory(inventory, source_audit, output_dir, PROFILE)
    mapping, revision = load_romanization_map(romanization_map, devanagari_tokens)
    profile = replace(
        PROFILE,
        source=replace(SOURCE, resolver_revision="jk-hindi-elector-resolver-v4"),
        description=(
            "Active assembly rows with exact native corroboration. A caller-supplied "
            "local map adds Latin surname forms after selection. Unmapped selections "
            "keep their native evidence and null Latin fields."
        ),
        limitations=(
            *LIMITATIONS,
            "Latin forms come from the supplied map; format checks do not establish "
            "transliteration accuracy. No spelling merge, lookup or model promotion.",
        ),
    )
    return resolve_inventory(
        inventory,
        source_audit,
        output_dir,
        profile,
        romanize_token=mapping.get,
        romanization_revision=revision,
    )
