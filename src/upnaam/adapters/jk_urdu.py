"""Native corroboration from glyph-verified 2018 J&K Urdu electoral records."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any

from upnaam.adapters.arabic import arabic_character, arabic_tokens
from upnaam.adapters.electors import ElectorSource
from upnaam.adapters.jk_inventory import (
    InventoryProfile,
    load_romanization_map,
    resolve_inventory,
)

SOURCE = ElectorSource(
    state="jammu_kashmir_ladakh",
    source_revision="jk-urdu-2018-arial",
    resolver_revision="jk-urdu-elector-resolver-v1",
    name_source_column="elector_name_source",
    relation_source_column="relative_name_source",
    evidence_script="arabic",
    record_key_column="entry_event_key",
    zero_house_is_missing=True,
    preserve_house_separators=True,
    reject_evidence_conflicts=True,
    exact_spelling=True,
    confidence_diagnostic=False,
)


def _accepted_name(value: object, issue: object) -> str | None:
    if not isinstance(value, str) or issue is not None or not value.strip():
        return None
    if value != unicodedata.normalize("NFKC", value):
        return None
    if any(arabic_character(char) and char.isalpha() for char in value) and all(
        arabic_character(char) or char in " .-'\u2019" for char in value
    ):
        return value
    return None


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


PROFILE = InventoryProfile(
    source=SOURCE,
    language="Urdu",
    parser_filename="jk_urdu_unicode.py",
    filename_pattern=r"UACA(0(?:31|32|34))PS([0-9]{4})\.pdf",
    relationships={
        "باپ": "father",
        "والد": "father",
        "ماں": "mother",
        "والدہ": "mother",
        "خاوند": "husband",
    },
    accept_name=_accepted_name,
    accept_house=_accepted_house,
    description=(
        "Every active assembly record from the audited Urdu AC031/032/034 inventory, "
        "including missing names. Only glyph-verified names supply exact native "
        "evidence. Zero houses provide no household evidence. Latin fields stay null."
    ),
    limitations=(
        "Historical Urdu AC031, AC032 and AC034 only; not full-state coverage.",
        "Glyph checks validate transcription, not hereditary surnames.",
        "Shared given names can corroborate; surname accuracy is unmeasured.",
        "Missing, uncorroborated or conflicting evidence abstains; confidence is null.",
        "Relative-only candidates stay separate from recorded selections.",
        "No transliteration, spelling merge, lookup or model promotion.",
    ),
    module_path=Path(__file__),
)


NASTALEEQ_PROFILE = replace(
    PROFILE,
    source=replace(SOURCE, source_revision="jk-urdu-2018-nastaleeq"),
    parser_filename="jk_urdu_nastaleeq.py",
    filename_pattern=r"UACA(0(?:0[1-9]|[1-7][0-9]|8[0-7]))PS([0-9]{4})\.pdf",
    description=(
        "Every active assembly row from the audited Nastaleeq recovery inventory. "
        "Accepted native names supply exact evidence; missing relatives and "
        "households cannot corroborate a selection."
    ),
    limitations=(
        "Historical Urdu source partitions; accepted-name coverage is incomplete.",
        *PROFILE.limitations[1:],
    ),
)


CALIBRATED_PROFILE = replace(
    NASTALEEQ_PROFILE,
    source=replace(
        SOURCE,
        source_revision="jk-urdu-2018-calibrated",
        resolver_revision="jk-urdu-elector-resolver-v3",
    ),
    parser_filename="promote_jk_urdu.py",
    description=(
        "Every active assembly row from the audited full J&K Urdu inventory. "
        "Names recovered by glyph verification or the calibrated word-vote gate "
        "supply exact native evidence; unsupported fields remain null."
    ),
    limitations=(
        "Historical 2018 Urdu source partitions; not current population coverage.",
        "The calibrated word-vote gate scored 95.23% on hidden word controls.",
        "Hidden word controls measure transcription, not hereditary surnames.",
        *PROFILE.limitations[3:],
    ),
)


def resolve_jk_urdu(
    inventory: Path,
    source_audit: Path,
    output_dir: Path,
    *,
    romanization_map: Path | None = None,
) -> dict[str, Any]:
    """Preserve active assembly rows and resolve exact native Urdu evidence.

    Args:
        inventory: Glyph-verified reconciled inventory Parquet.
        source_audit: Parser audit with source hashes and per-part counts.
        output_dir: New directory for the restricted output artifacts.
        romanization_map: Optional local JSON token map applied after native selection.

    Returns:
        Source validation, exclusions, evidence counts and artifact hashes.
    """
    audit = json.loads(source_audit.read_text())
    scripts = audit.get("script_sha256", {})
    if CALIBRATED_PROFILE.parser_filename in scripts:
        profile = CALIBRATED_PROFILE
    elif NASTALEEQ_PROFILE.parser_filename in scripts:
        profile = NASTALEEQ_PROFILE
    else:
        profile = PROFILE
    if romanization_map is None:
        return resolve_inventory(inventory, source_audit, output_dir, profile)
    mapping, revision = load_romanization_map(romanization_map, arabic_tokens)
    mapped_revision = (
        "jk-urdu-elector-resolver-v4"
        if profile is CALIBRATED_PROFILE
        else "jk-urdu-elector-resolver-v2"
    )
    profile = replace(
        profile,
        source=replace(profile.source, resolver_revision=mapped_revision),
        description=(
            "Active assembly rows with exact native Urdu corroboration. A supplied "
            "local map adds Latin forms after selection; unmapped selections retain "
            "native evidence and null Latin fields."
        ),
        limitations=(
            *profile.limitations[:-1],
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
