"""Transparent positional surname candidate rules."""

from __future__ import annotations

from dataclasses import dataclass

from upnaam.normalization import NameToken, tokenize_name

PREFIX_HONORIFICS = frozenset(
    {
        "श्री",
        "श्रीमती",
        "सुश्री",
        "डॉ",
        "shri",
        "sri",
        "srimati",
        "smt",
        "mr",
        "mrs",
        "ms",
        "dr",
    }
)


@dataclass(frozen=True, slots=True)
class SurnameCandidateResult:
    """Candidates produced without choosing a state-specific name order."""

    tokens: tuple[NameToken, ...]
    eligible_tokens: tuple[NameToken, ...]
    first_candidate: NameToken | None
    last_candidate: NameToken | None
    surname: NameToken | None
    abstained: bool
    abstention_reason: str | None


def _drop_prefix_honorifics(tokens: tuple[NameToken, ...]) -> tuple[NameToken, ...]:
    first = 0
    while first < len(tokens) and tokens[first].normalized in PREFIX_HONORIFICS:
        first += 1
    return tokens[first:]


def extract_surname_candidates(
    value: object, *, min_letters: int = 2
) -> SurnameCandidateResult:
    """Apply the approved simple positional candidate rules.

    Args:
        value: Source name value.
        min_letters: Minimum alphabetic characters for surname candidacy.

    Returns:
        First and last eligible candidates plus the last-token baseline. A
        single eligible token is retained as a candidate but the baseline
        abstains rather than declaring it a surname.

    Raises:
        ValueError: If ``min_letters`` is less than one.
    """
    if min_letters < 1:
        raise ValueError("min_letters must be at least one")
    tokens = tokenize_name(value)
    after_prefix = _drop_prefix_honorifics(tokens)
    eligible = tuple(
        token for token in after_prefix if token.letter_count >= min_letters
    )
    first = eligible[0] if eligible else None
    last = eligible[-1] if eligible else None
    if not eligible:
        reason = "missing-name" if not tokens else "no-eligible-token"
        return SurnameCandidateResult(tokens, eligible, None, None, None, True, reason)
    if len(eligible) == 1:
        return SurnameCandidateResult(
            tokens, eligible, first, last, None, True, "single-token-name"
        )
    return SurnameCandidateResult(tokens, eligible, first, last, last, False, None)
