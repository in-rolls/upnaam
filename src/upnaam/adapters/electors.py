"""Elector-level surname artifacts from parsed electoral rolls, by corroboration.

One builder for every roll parsed to the parsed-rolls column set (one row per printed
elector box with name, relation type and name, house number, part and the DELETED
stamp). The resolver is :mod:`upnaam.corroboration`: electors at one house in one part
are a household, and the surname is the token corroborated by a co-resident, the
relation name or (where the roll prints one) the house name. Each state's source is a
:class:`ElectorSource`: which columns hold the Latin names, whether the house field is
evidence, and the position rule, if any, for the uncorroborated rungs.

Telangana (English rolls of the 2017 SSR and 2018 draft, doi:10.7910/DVN/OG47IV) has no
position rule: the rolls mix surname-first and surname-last names within one part, so
uncorroborated multi-token names abstain with ``no-evidence``. Lakshadweep (SIR Final
Roll 2026, Malayalam, romanized) has no position rule either, and its house field is
evidence: the roll prints a house name and people go by it.

For Telangana and Lakshadweep, ``surname_confidence`` records a within-roll
agreement diagnostic, not independently measured accuracy. For
a corroborated surname it is the agreement between the two evidence sources where both
exist (a household pick that the relation name also carries, over household picks that
had a relation-shared token at all). For a position-rule pick it is the share of
corroborated surnames that sit in that position, which is what the rule would have
scored. Relative candidates remain separate from recorded surnames and this
diagnostic. Karnataka leaves this field null pending external validation.

The artifacts are restricted (person-level); the code and the aggregate audit are what
the repository commits.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, replace
from operator import eq
from typing import TYPE_CHECKING, Literal

import pyarrow as pa
import pyarrow.parquet as pq

from upnaam.corroboration import (
    CORROBORATION_REVISION,
    CorroboratedSurname,
    conservative_same_spelling,
    content_tokens,
    resolve_household,
    same_spelling,
)
from upnaam.normalization import (
    NORMALIZATION_REVISION,
    normalize_latin_token,
    normalize_name,
)
from upnaam.relative import RELATIVE_INFERENCE_REVISION, suggest_relative_surnames
from upnaam.schema import CANONICALIZATION_REVISION, CanonicalizationStatus

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

ACTIVE_SECTIONS = ("main", "addition")
CORROBORATED = ("household_and_relation", "household", "relation", "house")


@dataclass(frozen=True)
class ElectorSource:
    """How one state's parsed roll maps onto the resolver."""

    state: str
    source_revision: str
    resolver_revision: str
    #: Columns holding the Latin-script name, relation name and house field.
    name_column: str = "elector_name"
    relation_column: str = "father_or_husband_name"
    house_column: str = "house_no"
    #: Columns holding the roll's own script, kept beside the Latin ones; ``None`` when
    #: the roll is printed in Latin script.
    name_source_column: str | None = None
    relation_source_column: str | None = None
    #: Whether the house field's tokens corroborate a surname.
    house_evidence: bool = False
    #: The position rule for the uncorroborated rungs; ``None`` abstains on them.
    position: str | None = None
    zero_house_is_missing: bool = False
    token_romanization: bool = False
    preserve_house_separators: bool = False
    relative_position: str | None = None
    reject_evidence_conflicts: bool = False
    exact_spelling: bool = False
    confidence_diagnostic: bool = True
    evidence_script: Literal["latin", "devanagari", "arabic"] = "latin"
    record_key_column: str | None = None


SOURCES: dict[str, ElectorSource] = {
    "andhra": ElectorSource(
        state="andhra",
        source_revision="og47iv-andhra-2017",
        resolver_revision="andhra-elector-resolver-v1",
        zero_house_is_missing=True,
    ),
    "karnataka": ElectorSource(
        state="karnataka",
        source_revision="og47iv-karnataka-2017",
        resolver_revision="karnataka-elector-resolver-v4",
        name_column="elector_name_en",
        relation_column="father_or_husband_name_en",
        name_source_column="elector_name",
        relation_source_column="father_or_husband_name",
        zero_house_is_missing=True,
        token_romanization=True,
        preserve_house_separators=True,
    ),
    "telangana": ElectorSource(
        state="telangana",
        source_revision="og47iv-telangana-english-2017",
        resolver_revision="telangana-elector-resolver-v2",
    ),
    "lakshadweep": ElectorSource(
        state="lakshadweep",
        source_revision="lakshadweep-final-roll-2026",
        resolver_revision="lakshadweep-elector-resolver-v2",
        name_column="elector_name_en",
        relation_column="father_or_husband_name_en",
        house_column="house_no_en",
        name_source_column="elector_name",
        relation_source_column="father_or_husband_name",
        house_evidence=True,
    ),
}

OUTPUT_SCHEMA = pa.schema(
    [
        ("elector_id", pa.string()),
        ("source_elector_id", pa.string()),
        ("source_number", pa.string()),
        ("state", pa.string()),
        ("year", pa.string()),
        ("filename", pa.string()),
        ("part_no", pa.string()),
        ("household_id", pa.string()),
        ("household_size", pa.int32()),
        ("house_no_raw", pa.string()),
        ("age_raw", pa.string()),
        ("sex_raw", pa.string()),
        ("relationship_raw", pa.string()),
        ("name_source_raw", pa.string()),
        ("relative_name_source_raw", pa.string()),
        ("name_latin_raw", pa.string()),
        ("relative_name_latin_raw", pa.string()),
        ("ac_name_source_raw", pa.string()),
        ("district_source_raw", pa.string()),
        ("ac_name_latin_raw", pa.string()),
        ("district_latin_raw", pa.string()),
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
        ("surname_confidence", pa.float64()),
        ("abstained", pa.bool_()),
        ("abstention_reason", pa.string()),
        ("normalization_revision", pa.string()),
        ("resolver_revision", pa.string()),
        ("corroboration_revision", pa.string()),
        ("relative_surname_candidate", pa.string()),
        ("relative_surname_raw", pa.string()),
        ("relative_surname_relationship", pa.string()),
        ("relative_surname_evidence", pa.string()),
        ("relative_surname_abstention_reason", pa.string()),
        ("relative_inference_revision", pa.string()),
    ]
)


@dataclass
class ElectorArtifactReport:
    """Aggregate evidence returned by the artifact builder."""

    state: str
    rows: int
    households: int
    evidence: dict[str, int]
    position_by_evidence: dict[str, dict[str, int]]
    abstention_reasons: dict[str, int]
    confidence: dict[str, float]
    relation_agreement_checked: int
    relation_agreement: int
    romanization_revision: str | None = None

    def to_json(self) -> dict[str, object]:
        """Serializable report."""
        return asdict(self)


def household_key(
    filename: str,
    house: object,
    *,
    zero_is_missing: bool = False,
    preserve_separators: bool = False,
) -> str | None:
    """The household identity: the part and the house field, punctuation dropped.

    Dropping punctuation and case is what makes "1/22 A", "1:22a" and "1-22 a" one
    house; the separator is the roll's or the OCR's, not the household's.
    """
    surface = unicodedata.normalize("NFC", str(house or "")).casefold()
    if preserve_separators:
        surface = "".join(
            str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in surface
        )
        surface = re.sub(r"(?<=\d)\s+(?=\d)", "/", surface)
        surface = re.sub(r"[/\\:;\-\u2013\u2014]+", "/", surface)
    house = "".join(
        ch
        for ch in surface
        if ch.isalnum()
        or unicodedata.category(ch).startswith("M")
        or (preserve_separators and ch == "/")
    )
    house = house.strip("/")
    if (
        zero_is_missing
        and house
        and all(ch == "/" or unicodedata.decimal(ch, -1) == 0 for ch in house)
    ):
        return None
    return f"{filename}:{house}" if house else None


def confidence_table(
    position_by_evidence: dict[str, dict[str, int]], checked: int, agree: int
) -> dict[str, float]:
    """Measured confidence per rung.

    ``corroborated`` is the share of household picks that the relation name confirmed,
    among those that could be checked. ``first``, ``middle`` and ``last`` are the shares
    of corroborated surnames sitting in that position: what a position rule scores here.
    """
    corroborated: Counter[str] = Counter()
    for evidence in CORROBORATED:
        corroborated.update(position_by_evidence.get(evidence, {}))
    total = sum(corroborated.values())
    table = (
        {pos: corroborated[pos] / total for pos in ("first", "middle", "last")}
        if total
        else {}
    )
    if checked:
        table["corroborated"] = agree / checked
    return table


def _row(
    spec: ElectorSource,
    source: dict[str, object],
    result: CorroboratedSurname,
    household_id: str | None,
    household_size: int,
    romanize_token: Callable[[str], str | None] | None = None,
) -> dict[str, object]:
    native = spec.evidence_script in {"devanagari", "arabic"}
    latin = (
        normalize_latin_token(result.surname) if result.surname and not native else None
    )
    latin_raw = result.surname_raw if latin else None
    if native and result.surname and romanize_token is not None:
        latin_raw = romanize_token(result.surname)
        if latin_raw is not None:
            if not isinstance(latin_raw, str) or not re.fullmatch(
                r"[A-Za-z]{2,}", latin_raw
            ):
                raise ValueError(
                    "Native romanization must return one ASCII letter token"
                )
            latin = latin_raw.lower()
    if spec.token_romanization and result.surname_raw:
        latin_raw = (
            result.surname_raw
            if result.surname_raw.isascii()
            else romanize_token(result.surname_raw)
            if romanize_token
            else None
        )
    geography = {
        key: value
        if isinstance(value := source.get(key), str) and value.isascii()
        else None
        for key in ("ac_name", "district")
    }
    return {
        "elector_id": f"{spec.source_revision}:{source['record_key']}",
        "source_elector_id": source.get("id"),
        "source_number": source.get("number"),
        "state": spec.state,
        "year": source.get("year"),
        "filename": source.get("filename"),
        "part_no": source.get("part_no"),
        "household_id": household_id,
        "household_size": household_size,
        "house_no_raw": source.get("house_no"),
        "age_raw": source.get("age"),
        "sex_raw": source.get("sex"),
        "relationship_raw": source.get("relationship_source")
        or source.get("relationship"),
        "name_source_raw": source.get("name_source"),
        "relative_name_source_raw": source.get("relation_source"),
        "name_latin_raw": None if native else source.get("name"),
        "relative_name_latin_raw": None if native else source.get("relation"),
        "ac_name_source_raw": source.get("ac_name"),
        "district_source_raw": source.get("district"),
        "ac_name_latin_raw": geography["ac_name"],
        "district_latin_raw": geography["district"],
        "surname_raw": result.surname_raw,
        "surname_source_normalized": normalize_name(result.surname_raw)
        if spec.token_romanization
        else result.surname,
        "surname_latin_raw": latin_raw,
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
            else "latin_form_unavailable"
            if result.surname
            else "surname_not_selected"
        ),
        "canonicalization_provenance": None,
        "canonicalization_revision": CANONICALIZATION_REVISION,
        "surname_position": result.position,
        "surname_provenance": (
            f"{result.evidence}_shared_token"
            if result.evidence in CORROBORATED
            else "initials_single_token"
            if spec.token_romanization and result.evidence == "position"
            else result.evidence
        ),
        "surname_evidence": result.evidence,
        "surname_confidence": None,  # filled once the state's confidence table is known
        "abstained": result.abstained,
        "abstention_reason": result.abstention_reason,
        "normalization_revision": NORMALIZATION_REVISION,
        "resolver_revision": spec.resolver_revision,
        "corroboration_revision": CORROBORATION_REVISION,
    }


def _select_sql(spec: ElectorSource, columns: set[str]) -> str:
    def col(name: str | None, alias: str) -> str:
        return f"{name}::VARCHAR AS {alias}" if name else f"NULL AS {alias}"

    # a roll without supplement components has no roll_section column
    section = (
        f"roll_section IN {ACTIVE_SECTIONS} AND " if "roll_section" in columns else ""
    )
    raw_relationship = col(
        "relationship_source" if "relationship_source" in columns else "relationship",
        "relationship_source",
    )
    source_columns = ", ".join(
        col(name, name)
        for name in (
            "number",
            "id",
            "relationship",
            "house_no",
            "age",
            "sex",
            "ac_name",
            "district",
            "part_no",
            "year",
            "filename",
        )
    )
    record_key = (
        f"{spec.record_key_column}::VARCHAR"
        if spec.record_key_column
        else "filename || ':' || number::VARCHAR"
    )
    return (
        f"SELECT {source_columns}, {record_key} AS record_key, "  # noqa: S608 - fixed column names
        f"       {raw_relationship}, "
        f"       {col(spec.name_column, 'name')}, "
        f"       {col(spec.relation_column, 'relation')}, "
        f"       {col(spec.house_column, 'house')}, "
        f"       {col(spec.name_source_column, 'name_source')}, "
        f"       {col(spec.relation_source_column, 'relation_source')} "
        "FROM read_parquet(?, union_by_name = true) "
        f"WHERE {section}NOT coalesce(deleted, false) "
        "ORDER BY filename, "
        "  upnaam_household_key(filename, house_no), "
        "  number::INT, record_key"
    )


def build_elector_artifact(
    spec: ElectorSource,
    electors_path: Path,
    output_path: Path,
    *,
    position: str | None = None,
    batch_parts: int = 200,
    romanize_token: Callable[[str], str | None] | None = None,
    romanization_revision: str | None = None,
) -> ElectorArtifactReport:
    """Resolve every active elector in the parsed roll and write the artifact.

    Args:
        spec: The state's source description.
        electors_path: The parsed roll (``electors.parquet``).
        output_path: Destination person-level Parquet path.
        position: A position rule for the uncorroborated rungs, overriding the spec's.
        batch_parts: Parts resolved per output row group.
        romanize_token: Local token lookup, required for Kannada evidence. With
            native evidence, applied only after native selection.
        romanization_revision: Immutable hash identifying that lookup.

    Returns:
        Evidence shares, the position table and the confidence table.

    Raises:
        ValueError: The evidence mode has an incompatible lookup or inference policy.
        BaseException: Re-raises source or output failures after removing the
            incomplete output artifact.
    """
    import duckdb
    from duckdb.func import FunctionNullHandling

    tokenizer = content_tokens
    if spec.evidence_script in {"devanagari", "arabic"}:
        from upnaam.adapters.arabic import arabic_tokens
        from upnaam.adapters.devanagari import devanagari_tokens

        if (
            spec.token_romanization
            or position
            or spec.position
            or spec.relative_position
            or spec.house_evidence
            or not spec.exact_spelling
            or not spec.reject_evidence_conflicts
            or spec.confidence_diagnostic
        ):
            raise ValueError(
                f"{spec.evidence_script.title()} evidence requires exact corroboration "
                "without Latin or position inference"
            )
        if bool(romanize_token) != bool(romanization_revision):
            raise ValueError("Native romanization requires a lookup and its revision")
        tokenizer = (
            devanagari_tokens if spec.evidence_script == "devanagari" else arabic_tokens
        )
    spelling_matcher = (
        eq
        if spec.exact_spelling
        else conservative_same_spelling
        if spec.token_romanization
        else same_spelling
    )
    native_tokenizer = None
    if spec.token_romanization:
        from upnaam.adapters.kannada import KannadaEvidenceTokens

        if romanize_token is None or not romanization_revision:
            raise ValueError("Karnataka requires a local token lookup and its revision")
        if position:
            raise ValueError(
                "Token romanization requires corroboration, not a position rule"
            )
        native_tokenizer = KannadaEvidenceTokens(romanize_token)
        tokenizer = native_tokenizer
    position = position or spec.position
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    con = duckdb.connect()

    def source_household_key(filename: str, house: object) -> str | None:
        return household_key(
            filename,
            house,
            zero_is_missing=spec.zero_house_is_missing,
            preserve_separators=spec.preserve_house_separators,
        )

    con.create_function(
        "upnaam_household_key",
        source_household_key,
        ["VARCHAR", "VARCHAR"],
        "VARCHAR",
        null_handling=FunctionNullHandling.SPECIAL,
    )
    present = {
        row[0]
        for row in con.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [str(electors_path)]
        ).fetchall()
    }
    rel = con.execute(_select_sql(spec, present), [str(electors_path)])
    columns = [d[0] for d in rel.description]
    writer = pq.ParquetWriter(temporary, OUTPUT_SCHEMA, compression="zstd")
    evidence: Counter[str] = Counter()
    position_by_evidence: dict[str, Counter[str]] = {}
    abstentions: Counter[str] = Counter()
    checked = agree = rows_written = households = 0
    pending: list[dict[str, object]] = []
    pending_parts = 0
    current_part: str | None = None

    def flush(household: list[dict[str, object]]) -> None:
        nonlocal checked, agree, households
        initials_candidates = [
            native_tokenizer.initials_candidate(r["name_source"])
            if native_tokenizer
            else None
            for r in household
        ]
        single_names = [
            bool(
                native_tokenizer
                and r["name_source"]
                and not native_tokenizer.has_multiple_words(r["name_source"])
                and candidate is None
            )
            for r, candidate in zip(household, initials_candidates, strict=True)
        ]
        members = [
            (None if single else r["name_source"], r["relation_source"])
            if spec.token_romanization
            else (r["name"], r["relation"])
            for r, single in zip(household, single_names, strict=True)
        ]
        houses = [r["house"] for r in household] if spec.house_evidence else None
        key = source_household_key(
            str(household[0]["filename"]), household[0]["house_no"]
        )
        results = (
            resolve_household(
                members,
                position=position,
                houses=houses,
                tokenizer=tokenizer,
                spelling_matcher=spelling_matcher,
                reject_evidence_conflicts=spec.token_romanization
                or spec.reject_evidence_conflicts,
            )
            if key
            else [
                resolve_household(
                    [m],
                    position=position,
                    houses=[h] if houses else None,
                    tokenizer=tokenizer,
                    spelling_matcher=spelling_matcher,
                    reject_evidence_conflicts=spec.token_romanization
                    or spec.reject_evidence_conflicts,
                )[0]
                for m, h in zip(members, houses or [None] * len(members), strict=True)
            ]
        )
        results = [
            replace(result, abstention_reason="single-name-token") if single else result
            for result, single in zip(results, single_names, strict=True)
        ]
        results = [
            CorroboratedSurname(
                candidate.normalized, candidate.raw, "position", "last", None
            )
            if candidate is not None and result.abstention_reason == "no-evidence"
            else result
            for result, candidate in zip(results, initials_candidates, strict=True)
        ]
        candidate_members = [
            (r["name_source"], r["relation_source"])
            if spec.token_romanization
            else (r["name"], r["relation"])
            for r in household
        ]
        relationships = [r["relationship"] for r in household]
        candidates = (
            suggest_relative_surnames(
                candidate_members,
                results,
                relationships=relationships,
                relative_position=spec.relative_position,
                tokenizer=tokenizer,
            )
            if key
            else [
                suggest_relative_surnames(
                    [member],
                    [result],
                    relationships=[relationship],
                    relative_position=spec.relative_position,
                    tokenizer=tokenizer,
                )[0]
                for member, result, relationship in zip(
                    candidate_members, results, relationships, strict=True
                )
            ]
        )
        households += bool(key)
        for source, result, member, candidate in zip(
            household, results, members, candidates, strict=True
        ):
            evidence[result.evidence or "abstained"] += 1
            if result.evidence:
                position_by_evidence.setdefault(result.evidence, Counter())[
                    result.position or "none"
                ] += 1
            if result.abstention_reason:
                abstentions[result.abstention_reason] += 1
            # the relation name as an independent read of a household-corroborated
            # surname: agreement is the household_and_relation rung; a household-only
            # pick beside a relation-shared token is a disagreement by construction
            if result.evidence == "household_and_relation":
                checked += 1
                agree += 1
            elif result.evidence == "household":
                rel_tokens = {t.normalized for t in tokenizer(member[1])}
                own = {t.normalized for t in tokenizer(member[0])}
                if own & rel_tokens:
                    checked += 1
            row = _row(spec, source, result, key, len(household), romanize_token)
            row.update(
                relative_surname_candidate=candidate.surname,
                relative_surname_raw=candidate.surname_raw,
                relative_surname_relationship=candidate.relationship,
                relative_surname_evidence=candidate.evidence,
                relative_surname_abstention_reason=candidate.abstention_reason,
                relative_inference_revision=RELATIVE_INFERENCE_REVISION,
            )
            pending.append(row)

    try:
        household: list[dict[str, object]] = []
        hkey: str | None = None
        while batch := rel.fetchmany(50_000):
            for values in batch:
                source = dict(zip(columns, values, strict=True))
                k = source_household_key(
                    str(source["filename"]), source["house_no"]
                ) or (f"#{source['record_key']}")
                if k != hkey:
                    if household:
                        flush(household)
                    household, hkey = [], k
                    if current_part != source["filename"]:
                        current_part = str(source["filename"])
                        pending_parts += 1
                        if pending_parts % batch_parts == 0 and pending:
                            writer.write_table(
                                pa.Table.from_pylist(pending, schema=OUTPUT_SCHEMA)
                            )
                            rows_written += len(pending)
                            pending = []
                household.append(source)
        if household:
            flush(household)
        if pending:
            writer.write_table(pa.Table.from_pylist(pending, schema=OUTPUT_SCHEMA))
            rows_written += len(pending)
    except BaseException:
        writer.close()
        temporary.unlink(missing_ok=True)
        raise
    writer.close()
    report = ElectorArtifactReport(
        state=spec.state,
        rows=rows_written,
        households=households,
        evidence=dict(evidence),
        position_by_evidence={k: dict(v) for k, v in position_by_evidence.items()},
        abstention_reasons=dict(abstentions),
        confidence=(
            {}
            if spec.token_romanization or not spec.confidence_diagnostic
            else confidence_table(
                {k: dict(v) for k, v in position_by_evidence.items()}, checked, agree
            )
        ),
        relation_agreement_checked=checked,
        relation_agreement=agree,
        romanization_revision=romanization_revision,
    )
    _stamp_confidence(temporary, output_path, report)
    return report


def _stamp_confidence(
    temporary: Path, output_path: Path, report: ElectorArtifactReport
) -> None:
    """Second pass: fill ``surname_confidence`` from the state's measured table."""
    import duckdb

    conf = report.confidence
    rungs = ", ".join(f"'{e}'" for e in CORROBORATED)
    cases = (
        f"WHEN surname_evidence IN ({rungs}) THEN {conf['corroborated']}"
        if "corroborated" in conf
        else ""
    )
    position_rule = " ".join(
        f"WHEN surname_evidence = 'position' AND surname_position = '{pos}' "
        f"THEN {share}"
        for pos, share in conf.items()
        if pos in ("first", "middle", "last")
    )
    confidence_sql = (
        f"CAST(CASE {cases} {position_rule} ELSE NULL END AS DOUBLE)"
        if cases or position_rule
        else "NULL::DOUBLE"
    )
    con = duckdb.connect()
    con.execute(
        "COPY (SELECT * REPLACE ("  # noqa: S608 - fixed rungs and measured shares
        f"{confidence_sql} AS surname_confidence) "
        "FROM read_parquet($input_path)) "
        "TO $output_path (FORMAT parquet, COMPRESSION zstd)",
        {"input_path": str(temporary), "output_path": str(output_path)},
    )
    temporary.unlink(missing_ok=True)


def write_elector_audit(path: Path, report: ElectorArtifactReport) -> None:
    """Write the aggregate audit JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_json(), indent=2, sort_keys=True) + "\n")
