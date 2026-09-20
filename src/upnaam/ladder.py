"""Versioned surname decisions, candidates and matching evidence in three tables."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

from upnaam.corroboration import (
    CORROBORATION_REVISION,
    CorroboratedSurname,
    conservative_same_spelling,
    content_tokens,
    resolve_household,
    same_spelling,
    spelling_slack,
)
from upnaam.matching import MatchPolicy, compare_strings
from upnaam.normalization import NORMALIZATION_REVISION, NameToken, normalize_name
from upnaam.relative import suggest_relative_surnames

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

LADDER_REVISION = "surname-ladder-v1"
SPAN_CONVENTION = "zero-based Python Unicode code points; end exclusive"


def _schema(strings: str, extra: list[tuple[str, pa.DataType]]) -> pa.Schema:
    return pa.schema([(name, pa.string()) for name in strings.split()] + extra)


RESOLUTION_SCHEMA = _schema(
    "record_id source_revision state year household_id own_name_raw relative_name_raw "
    "explicit_surname_raw house_name_raw "
    "relationship_raw relationship_type recorded_candidate_id selected_candidate_id "
    "resolution_status rule_id policy_revision ladder_revision calibration_revision",
    [("reason_codes", pa.list_(pa.string())), ("p_correct", pa.float64())],
)
CANDIDATE_SCHEMA = _schema(
    "candidate_id record_id scope_id origin source_record_id source_revision "
    "source_field script "
    "source_value surname_raw surname_source_normalized surname_latin_raw "
    "surname_latin_normalized comparison_value normalization_revision "
    "transliteration_revision surname_canonical cluster_id cluster_revision "
    "canonicalization_status canonicalization_rule candidate_status rule_id",
    [
        ("token_start", pa.int64()),
        ("token_end", pa.int64()),
        ("reason_codes", pa.list_(pa.string())),
    ],
)
EVIDENCE_SCHEMA = _schema(
    "event_id record_id scope_id candidate_id stage rule_id reason_code "
    "left_value right_value metric parameters edit_operations metric_revision "
    "matching_revision representation_revision details",
    [
        ("metric_value", pa.float64()),
        ("threshold", pa.float64()),
        ("accepted", pa.bool_()),
    ],
)


@dataclass(frozen=True, slots=True)
class NameRecord:
    """One source-qualified person with untouched source fields."""

    record_id: str
    source_revision: str
    state: str
    year: str
    name: str | None
    relative_name: str | None = None
    relationship: str | None = None
    household_id: str | None = None
    house_name: str | None = None
    explicit_surname: str | None = None


@dataclass(frozen=True, slots=True)
class LinkedSurname:
    """A separately labeled surname span on a uniquely linked same-person record."""

    record_id: str
    source_record_id: str
    source_revision: str
    source_value: str
    token_start: int
    token_end: int
    linkage_basis: str
    reference_kind: str

    def __post_init__(self) -> None:
        """Require an auditable source span and distinguish provisional references."""
        if not all(
            (
                self.record_id,
                self.source_record_id,
                self.source_revision,
                self.linkage_basis,
            )
        ):
            raise ValueError(
                "linked surnames require source identities and linkage basis"
            )
        if not 0 <= self.token_start < self.token_end <= len(self.source_value):
            raise ValueError("linked surname span is outside its source value")
        if self.reference_kind not in {
            "explicit_field",
            "adjudicated",
            "position_policy",
        }:
            raise ValueError("reference_kind must describe how the surname was labeled")
        if not any(
            c.isalpha() for c in self.source_value[self.token_start : self.token_end]
        ):
            raise ValueError("linked surname must contain letters")


@dataclass(frozen=True, slots=True)
class LadderPolicy:
    """Explicit source policy; no default surname position or inferred confidence."""

    revision: str
    position: str | None = None
    relative_position: str | None = None
    tokenization: str = "content"
    house_evidence: bool = False

    def __post_init__(self) -> None:
        """Reject unsupported or unversioned policy combinations."""
        if not self.revision.strip():
            raise ValueError("policy revision must be nonempty")
        if self.position not in (
            None,
            "first",
            "last",
        ) or self.relative_position not in (None, "first", "last"):
            raise ValueError("position policies must be first, last or None")
        if self.tokenization not in {"content", "kannada"}:
            raise ValueError("unsupported tokenization policy")
        if self.tokenization == "kannada" and self.position is not None:
            raise ValueError("Kannada requires corroboration or the initials exception")


@dataclass(frozen=True, slots=True)
class ResolutionBundle:
    """Typed tables with a single atomic, hash-bound artifact writer."""

    resolutions: pa.Table
    candidates: pa.Table
    evidence: pa.Table
    policy: LadderPolicy

    def write(self, directory: Path) -> None:
        """Write a new artifact directory, refusing to replace existing results.

        Args:
            directory: New destination containing three Parquet files and a manifest.

        Raises:
            FileExistsError: The destination already exists.
        """
        if directory.exists():
            raise FileExistsError(directory)
        directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory.parent) as temporary:
            staging = Path(temporary) / "artifact"
            staging.mkdir()
            artifacts = {}
            for name, table in (
                ("resolutions", self.resolutions),
                ("candidates", self.candidates),
                ("evidence", self.evidence),
            ):
                path = staging / f"{name}.parquet"
                pq.write_table(table, path, compression="zstd")
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                artifacts[path.name] = {"sha256": digest, "rows": table.num_rows}
            (staging / "manifest.json").write_text(
                json.dumps(
                    {
                        "ladder_revision": LADDER_REVISION,
                        "policy": asdict(self.policy),
                        "span_convention": SPAN_CONVENTION,
                        "artifacts": artifacts,
                        "accuracy": "unmeasured; matching scores are not probabilities",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            staging.rename(directory)


def _identifier(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()


def _whole_token(raw: str) -> NameToken:
    return NameToken(
        raw, normalize_name(raw) or "", 0, len(raw), sum(c.isalpha() for c in raw)
    )


class _Builder:
    def __init__(
        self,
        policy: LadderPolicy,
        romanize: Callable[[str], str | None] | None,
        revision: str | None,
    ):
        self.policy = policy
        self.romanize = romanize
        self.romanization_revision = revision
        self.resolutions: dict[str, dict[str, object]] = {}
        self.candidates: dict[str, dict[str, object]] = {}
        self.evidence: list[dict[str, object]] = []

    def _source_token(self, raw: str) -> NameToken:
        token = _whole_token(raw)
        if (
            self.policy.tokenization == "kannada"
            and self.romanize
            and not raw.isascii()
        ):
            latin = self.romanize(raw)
            if latin and latin.isascii():
                return replace(
                    token, normalized=normalize_name(latin) or token.normalized
                )
        return token

    def candidate(
        self,
        record: NameRecord,
        token: NameToken,
        field: str,
        value: str,
        *,
        origin: str = "own_written",
        source_record_id: str | None = None,
        source_revision: str | None = None,
    ) -> str:
        if value[token.start : token.end] != token.raw:
            raise ValueError("candidate token is not its claimed source span")
        candidate_id = _identifier(
            record.record_id,
            source_revision or record.source_revision,
            source_record_id or record.record_id,
            field,
            token.start,
            token.end,
            value,
        )
        latin_raw = (
            token.raw
            if token.raw.isascii()
            else self.romanize(token.raw)
            if self.romanize
            else None
        )
        latin_normalized = (
            normalize_name(latin_raw) if latin_raw and latin_raw.isascii() else None
        )
        self.candidates.setdefault(
            candidate_id,
            {
                "candidate_id": candidate_id,
                "record_id": record.record_id,
                "origin": origin,
                "scope_id": _identifier(
                    record.source_revision,
                    record.state,
                    record.year,
                    "house:" + record.household_id
                    if record.household_id
                    else "person:" + record.record_id,
                ),
                "script": "latin"
                if token.raw.isascii()
                else "kannada"
                if self.policy.tokenization == "kannada"
                else "unspecified",
                "source_record_id": source_record_id or record.record_id,
                "source_revision": source_revision or record.source_revision,
                "source_field": field,
                "source_value": value,
                "token_start": token.start,
                "token_end": token.end,
                "surname_raw": token.raw,
                "surname_source_normalized": normalize_name(token.raw),
                "surname_latin_raw": latin_raw,
                "surname_latin_normalized": latin_normalized,
                "comparison_value": token.normalized,
                "normalization_revision": NORMALIZATION_REVISION,
                "transliteration_revision": self.romanization_revision
                if not token.raw.isascii()
                else None,
                "surname_canonical": latin_normalized or normalize_name(token.raw),
                "cluster_id": None,
                "cluster_revision": None,
                "canonicalization_status": "identity_unmapped",
                "canonicalization_rule": None,
                "candidate_status": "retained_alternative",
                "rule_id": None,
                "reason_codes": [],
            },
        )
        return candidate_id

    def event(
        self,
        record_id: str | None,
        scope: str,
        stage: str,
        rule: str,
        *,
        candidate_id: str | None = None,
        accepted: bool | None = None,
        reason: str | None = None,
        comparison: dict[str, object] | None = None,
        details: object = None,
    ) -> None:
        self.evidence.append(
            {
                **(comparison or {}),
                "event_id": _identifier(scope, len(self.evidence)),
                "record_id": record_id,
                "scope_id": scope,
                "candidate_id": candidate_id,
                "stage": stage,
                "rule_id": rule,
                "accepted": accepted,
                "reason_code": reason,
                "representation_revision": (
                    f"{NORMALIZATION_REVISION}:{self.romanization_revision or 'native'}"
                ),
                "details": json.dumps(details, sort_keys=True),
            }
        )

    def group(
        self, records: list[NameRecord], references: dict[str, LinkedSurname]
    ) -> None:
        from upnaam.adapters.kannada import KannadaEvidenceTokens

        native = (
            KannadaEvidenceTokens(self.romanize)
            if self.policy.tokenization == "kannada" and self.romanize
            else None
        )
        tokenizer = native or content_tokens
        initials = [
            native.initials_candidate(r.name) if native else None for r in records
        ]
        single = [
            bool(
                native
                and r.name
                and not native.has_multiple_words(r.name)
                and initial is None
            )
            for r, initial in zip(records, initials, strict=True)
        ]
        members = [
            (None if short else r.name, r.relative_name)
            for r, short in zip(records, single, strict=True)
        ]
        trace: list[dict[str, object]] = []
        recorded = resolve_household(
            members,
            position=self.policy.position,
            houses=[r.house_name for r in records]
            if self.policy.house_evidence
            else None,
            tokenizer=tokenizer,
            spelling_matcher=conservative_same_spelling if native else same_spelling,
            reject_evidence_conflicts=True,
            trace=trace,
        )
        for index, (result, initial, short) in enumerate(
            zip(recorded, initials, single, strict=True)
        ):
            if short:
                recorded[index] = replace(result, abstention_reason="single-name-token")
            elif initial is not None and result.abstention_reason == "no-evidence":
                recorded[index] = CorroboratedSurname(
                    initial.normalized, initial.raw, "position", "last", None
                )
        scope = _identifier(
            records[0].source_revision,
            records[0].state,
            records[0].year,
            "house:" + records[0].household_id
            if records[0].household_id
            else "person:" + records[0].record_id,
        )
        canonical: dict[str, str] = {}
        selection: dict[int, dict[str, object]] = {}
        for event in trace:
            if event["stage"] == "surname_variant":
                left, right = str(event["left_value"]), str(event["right_value"])
                comparison = compare_strings(
                    left,
                    right,
                    MatchPolicy(
                        "levenshtein_distance",
                        spelling_slack(max(left, right, key=len)),
                        CORROBORATION_REVISION,
                    ),
                )
                if event["accepted"]:
                    canonical[right] = left
                self.event(
                    None,
                    scope,
                    "token_match",
                    str(event["rule_id"]),
                    accepted=bool(event["accepted"]),
                    reason="household_spelling_accepted"
                    if event["accepted"]
                    else "household_spelling_rejected",
                    comparison=comparison,
                    details=event,
                )
            else:
                selection[int(str(event["member_index"]))] = event
        recorded_ids: list[str | None] = []
        rules: list[str] = []
        for index, (record, result) in enumerate(zip(records, recorded, strict=True)):
            tokens = tokenizer(record.name)
            ids = [
                self.candidate(record, t, "own_name", record.name or "") for t in tokens
            ]
            for candidate_id, token in zip(ids, tokens, strict=True):
                anchor = canonical.get(token.normalized, token.normalized)
                candidate = self.candidates[candidate_id]
                candidate.update(
                    cluster_id=_identifier(scope, anchor),
                    cluster_revision=CORROBORATION_REVISION,
                )
                if anchor != token.normalized:
                    candidate.update(
                        surname_canonical=anchor,
                        canonicalization_status="variant_mapped",
                        canonicalization_rule="household_anchor_spelling",
                    )
            for token in tokenizer(record.relative_name):
                self.candidate(
                    record,
                    token,
                    "relative_name",
                    record.relative_name or "",
                    origin="relative",
                )
            selected_index = selection[index].get("selected_index")
            initial_fallback = (
                initials[index] is not None
                and result.evidence == "position"
                and selected_index is None
            )
            rule = (
                "initials_single_token"
                if initial_fallback
                else "position_policy"
                if result.evidence == "position"
                else result.evidence or "abstain"
            )
            selected = (
                ids[0]
                if initial_fallback
                else ids[int(str(selected_index))]
                if selected_index is not None and not result.abstained
                else None
            )
            if record.explicit_surname:
                explicit = self._source_token(record.explicit_surname)
                if not explicit.letter_count:
                    recorded[index] = CorroboratedSurname(
                        None, None, None, None, "invalid-explicit-surname"
                    )
                    selected, rule = None, "abstain"
                else:
                    explicit_id = self.candidate(
                        record, explicit, "explicit_surname", record.explicit_surname
                    )
                    if result.abstention_reason == "conflicting-evidence" or (
                        selected
                        and explicit.normalized
                        != self._source_token(result.surname_raw or "").normalized
                    ):
                        recorded[index] = CorroboratedSurname(
                            None, None, None, None, "conflicting-evidence"
                        )
                        selected, rule = None, "abstain"
                    else:
                        selected, rule = explicit_id, "explicit_surname_field"
                        recorded[index] = CorroboratedSurname(
                            explicit.normalized,
                            explicit.raw,
                            "explicit_surname_field",
                            "last",
                            None,
                        )
            recorded_ids.append(selected)
            rules.append(rule)
        relative_evidence_records = list(recorded)
        for index, record in enumerate(records):
            reference = references.get(record.record_id)
            if reference is None:
                continue
            raw = reference.source_value[reference.token_start : reference.token_end]
            result = recorded[index]
            if not result.abstained and normalize_name(
                result.surname_raw
            ) != normalize_name(raw):
                relative_evidence_records[index] = CorroboratedSurname(
                    None, None, None, None, "conflicting-evidence"
                )
            elif result.abstention_reason not in {
                "conflicting-evidence",
                "invalid-explicit-surname",
            } and reference.reference_kind in {"explicit_field", "adjudicated"}:
                relative_evidence_records[index] = CorroboratedSurname(
                    self._source_token(raw).normalized,
                    raw,
                    "same_person_external",
                    "last",
                    None,
                )
        relatives = suggest_relative_surnames(
            [(r.name, r.relative_name) for r in records],
            relative_evidence_records,
            relationships=[r.relationship for r in records],
            relative_position=self.policy.relative_position,
            tokenizer=tokenizer,
        )
        for index, (record, result, relative) in enumerate(
            zip(records, recorded, relatives, strict=True)
        ):
            recorded_id = recorded_ids[index]
            selected = recorded_id
            rule = rules[index]
            reason = result.abstention_reason
            status = (
                "recorded_selected"
                if selected
                else "conflict"
                if reason == "conflicting-evidence"
                else "abstained"
            )
            reference = references.get(record.record_id)
            if reference is not None:
                raw = reference.source_value[
                    reference.token_start : reference.token_end
                ]
                token = replace(
                    self._source_token(raw),
                    start=reference.token_start,
                    end=reference.token_end,
                )
                external_id = self.candidate(
                    record,
                    token,
                    "external_name",
                    reference.source_value,
                    origin="same_person_external",
                    source_record_id=reference.source_record_id,
                    source_revision=reference.source_revision,
                )
                if status == "conflict":
                    external_reason = "existing_conflict"
                elif (
                    selected
                    and self._source_token(result.surname_raw or "").normalized
                    != token.normalized
                ):
                    status, selected, rule, reason = (
                        "conflict",
                        None,
                        "abstain",
                        "external-surname-conflict",
                    )
                    external_reason = reason
                elif selected:
                    external_reason = "external_agrees_with_recorded"
                elif result.abstention_reason == "invalid-explicit-surname":
                    external_reason = "invalid_explicit_surname"
                else:
                    selected, rule, reason = external_id, "same_person_external", None
                    status = (
                        "external_candidate"
                        if reference.reference_kind == "position_policy"
                        else "external_recovered"
                    )
                    external_reason = (
                        "provisional_reference"
                        if status == "external_candidate"
                        else "same_person_reference"
                    )
                self.event(
                    record.record_id,
                    scope,
                    "person_link",
                    "same_person_external",
                    candidate_id=external_id,
                    accepted=status not in {"conflict", "abstained"},
                    reason=external_reason,
                    details=asdict(reference),
                )
            if (
                selected is None
                and status != "conflict"
                and reason != "invalid-explicit-surname"
                and relative.surname
            ):
                matches = [
                    t
                    for t in tokenizer(record.relative_name)
                    if t.raw == relative.surname_raw
                ]
                if len(matches) == 1:
                    selected = self.candidate(
                        record,
                        matches[0],
                        "relative_name",
                        record.relative_name or "",
                        origin="relative",
                    )
                    rule = (
                        "relative_recorded_surname"
                        if relative.evidence == "matched-relative-recorded-surname"
                        else "relative_position_policy"
                    )
                    status, reason = (
                        "relative_candidate",
                        "surname_transfer_unvalidated",
                    )
            self.event(
                record.record_id,
                scope,
                "relative_inference",
                relative.evidence or "abstain",
                accepted=status == "relative_candidate",
                reason=relative.abstention_reason or "surname_transfer_unvalidated",
                details={"relationship": relative.relationship},
            )
            if recorded_id:
                self.candidates[recorded_id].update(
                    candidate_status="recorded_selected", rule_id=rules[index]
                )
            if selected:
                self.candidates[selected].update(
                    candidate_status=status,
                    rule_id=rule,
                    reason_codes=[reason] if reason else [],
                )
            self.resolutions[record.record_id] = {
                "record_id": record.record_id,
                "source_revision": record.source_revision,
                "state": record.state,
                "year": record.year,
                "household_id": record.household_id,
                "own_name_raw": record.name,
                "explicit_surname_raw": record.explicit_surname,
                "house_name_raw": record.house_name,
                "relative_name_raw": record.relative_name,
                "relationship_raw": record.relationship,
                "relationship_type": normalize_name(record.relationship),
                "recorded_candidate_id": recorded_id,
                "selected_candidate_id": selected,
                "resolution_status": status,
                "rule_id": rule,
                "reason_codes": [reason] if reason else [],
                "policy_revision": self.policy.revision,
                "ladder_revision": LADDER_REVISION,
                "p_correct": None,
                "calibration_revision": None,
            }
            self.event(
                record.record_id,
                scope,
                "surname_selection",
                rule,
                candidate_id=selected,
                accepted=selected is not None,
                reason=reason,
                details=selection[index],
            )


def resolve_name_records(
    records: Sequence[NameRecord],
    *,
    policy: LadderPolicy,
    linked_surnames: Sequence[LinkedSurname] = (),
    romanize_token: Callable[[str], str | None] | None = None,
    romanization_revision: str | None = None,
) -> ResolutionBundle:
    """Resolve a batch of complete households into auditable surname artifacts.

    Args:
        records: Source-qualified records. Unknown household IDs must be null.
            Keep a household together when batching a larger source.
        policy: Versioned source and naming-pattern policy.
        linked_surnames: Independently established unique same-person references.
        romanize_token: Local Kannada token lookup for the Kannada policy.
        romanization_revision: Immutable lookup revision; required with a lookup.

    Returns:
        Resolution, candidate and evidence tables. Relative candidates remain
        provisional, and no matching score is reported as surname accuracy.

    Raises:
        ValueError: Identities, links or romanization provenance are invalid.
    """
    if bool(romanize_token) != bool(romanization_revision):
        raise ValueError("romanization lookup and revision must be supplied together")
    if policy.tokenization == "kannada" and romanize_token is None:
        raise ValueError("Kannada requires a local romanization lookup")
    identifiers = [r.record_id for r in records]
    if len(set(identifiers)) != len(identifiers) or any(
        not value.strip() for value in identifiers
    ):
        raise ValueError("record IDs must be unique nonempty strings")
    if any(
        not r.source_revision.strip() or not r.state.strip() or not r.year.strip()
        for r in records
    ):
        raise ValueError("source revision, state and year must be nonempty")
    references: dict[str, LinkedSurname] = {}
    external_ids = set()
    for reference in linked_surnames:
        key = (reference.source_revision, reference.source_record_id)
        if (
            reference.record_id not in identifiers
            or reference.record_id in references
            or key in external_ids
        ):
            raise ValueError(
                "external references must be unique one-to-one person links"
            )
        references[reference.record_id] = reference
        external_ids.add(key)
    groups: dict[tuple[str, str, str, str], list[NameRecord]] = defaultdict(list)
    for record in records:
        household = (
            "house:" + record.household_id
            if record.household_id
            else "person:" + record.record_id
        )
        groups[(record.source_revision, record.state, record.year, household)].append(
            record
        )
    builder = _Builder(policy, romanize_token, romanization_revision)
    for group in groups.values():
        builder.group(group, references)
    return ResolutionBundle(
        pa.Table.from_pylist(
            [builder.resolutions[key] for key in identifiers], schema=RESOLUTION_SCHEMA
        ),
        pa.Table.from_pylist(
            list(builder.candidates.values()), schema=CANDIDATE_SCHEMA
        ),
        pa.Table.from_pylist(builder.evidence, schema=EVIDENCE_SCHEMA),
        policy,
    )
