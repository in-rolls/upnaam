"""Lossless name normalization and tokenization."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_ZERO_WIDTH = re.compile("[\u200b-\u200d\ufeff]")
_DANDA = re.compile("[\u0964\u0965]")
_WHITESPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[^\s\u0964\u0965]+")
NORMALIZATION_REVISION = "normalization-v1"


@dataclass(frozen=True, slots=True)
class NameToken:
    """One token and its location in the untouched source string."""

    raw: str
    normalized: str
    start: int
    end: int
    letter_count: int

    @property
    def is_initial(self) -> bool:
        """Return whether the token contains exactly one alphabetic character."""
        return self.letter_count == 1


def normalize_name(value: object) -> str | None:
    """Create a conservative comparison form without transliteration.

    Args:
        value: Source value. Non-string and empty values are unsupported.

    Returns:
        NFC-normalized, case-folded text with formatting marks and repeated
        whitespace removed, or ``None`` for unsupported input.
    """
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFC", value)
    normalized = _ZERO_WIDTH.sub("", normalized)
    normalized = _DANDA.sub(" ", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip().casefold()
    return normalized or None


def tokenize_name(value: object) -> tuple[NameToken, ...]:
    """Tokenize a name while retaining raw substrings and source offsets.

    Args:
        value: Source name string.

    Returns:
        Immutable sequence of whitespace-delimited tokens. Internal hyphens,
        apostrophes, and punctuation are retained.
    """
    if not isinstance(value, str):
        return ()
    tokens: list[NameToken] = []
    for match in _TOKEN.finditer(value):
        raw = match.group(0)
        normalized = normalize_name(raw)
        if normalized is None:
            continue
        tokens.append(
            NameToken(
                raw=raw,
                normalized=normalized,
                start=match.start(),
                end=match.end(),
                letter_count=sum(character.isalpha() for character in normalized),
            )
        )
    return tuple(tokens)
