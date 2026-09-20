"""Relative-name candidates, kept separate from recorded surname selections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from upnaam.corroboration import content_tokens
from upnaam.normalization import normalize_name

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from upnaam.corroboration import CorroboratedSurname
    from upnaam.normalization import NameToken

RELATIVE_INFERENCE_REVISION = "relative-candidates-v1"
RELATIONSHIPS = frozenset({"father", "mother", "husband", "wife", "spouse"})
CORROBORATED = frozenset(
    {
        "household",
        "household_and_relation",
        "relation",
        "house",
        "explicit_surname_field",
        "same_person_external",
    }
)


@dataclass(frozen=True, slots=True)
class RelativeSurnameCandidate:
    """A possible family surname, without a claim of measured accuracy."""

    surname: str | None
    surname_raw: str | None
    relationship: str | None
    evidence: str | None
    abstention_reason: str | None


def suggest_relative_surnames(
    members: Sequence[tuple[object, object]],
    recorded: Sequence[CorroboratedSurname],
    *,
    relationships: Sequence[object],
    relative_position: str | None = None,
    tokenizer: Callable[[object], tuple[NameToken, ...]] = content_tokens,
) -> list[RelativeSurnameCandidate]:
    """Suggest candidates after recorded-name resolution, without updating its results.

    Args:
        members: Elector and relative names within one known household. Pass each
            person separately when household identity is missing.
        recorded: Results of the completed recorded-name pass, including initials.
        relationships: Explicit relationship types; unknown types cannot inherit.
        relative_position: Explicit first/last policy for relative names. With no
            policy, require one exact co-resident match with a corroborated surname.
        tokenizer: The same source-aware tokenizer as the recorded-name pass.

    Returns:
        One candidate or explicit abstention per elector. Candidates never become
        evidence for another candidate and never replace a recorded surname.

    Raises:
        ValueError: Inputs differ in length or the position policy is invalid.
    """
    if not len(members) == len(recorded) == len(relationships):
        raise ValueError("members, recorded and relationships must have equal lengths")
    if relative_position not in (None, "first", "last"):
        raise ValueError("relative_position must be first, last or None")
    names = [normalize_name(name) for name, _ in members]
    output = []
    for index, ((name, relative), result, relationship) in enumerate(
        zip(members, recorded, relationships, strict=True)
    ):
        relation = normalize_name(relationship)
        own_tokens, relative_tokens = tokenizer(name), tokenizer(relative)
        reason = None
        if not result.abstained:
            reason = "recorded-surname-available"
        elif result.abstention_reason == "conflicting-evidence":
            reason = "conflicting-evidence"
        elif relation not in RELATIONSHIPS:
            reason = "unsupported-relationship"
        elif len(own_tokens) != 1:
            reason = "requires-one-usable-elector-token"
        elif len(relative_tokens) < 2:
            reason = "relative-name-too-short"
        if reason:
            output.append(RelativeSurnameCandidate(None, None, relation, None, reason))
            continue

        matches = [
            other
            for other, normalized in enumerate(names)
            if other != index and normalized == normalize_name(relative)
        ]
        token = None
        evidence = None
        if len(matches) > 1:
            reason = "ambiguous-relative-match"
        elif matches:
            linked = recorded[matches[0]]
            if linked.evidence in CORROBORATED and not linked.abstained:
                token = next(
                    (t for t in relative_tokens if t.normalized == linked.surname), None
                )
                evidence = "matched-relative-recorded-surname" if token else None
            reason = None if token else "relative-surname-unresolved"
        elif relative_position:
            token = relative_tokens[0 if relative_position == "first" else -1]
            evidence = "relative-position-policy"
        else:
            reason = "no-relative-surname-evidence"
        output.append(
            RelativeSurnameCandidate(
                token.normalized if token else None,
                token.raw if token else None,
                relation,
                evidence,
                reason,
            )
        )
    return output
