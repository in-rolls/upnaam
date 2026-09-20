"""Exact Arabic-script tokens for native electoral-name corroboration."""

from __future__ import annotations

import unicodedata

from upnaam.normalization import NameToken, tokenize_name

TITLES = frozenset({"جناب", "محترمہ", "مسٹر"})


def arabic_character(char: str) -> bool:
    """Return whether a character is an Arabic-script letter or combining mark."""
    return (
        "ARABIC" in unicodedata.name(char, "")
        and unicodedata.category(char)[0] in "LM"
        and char != "\u0640"
    )


def arabic_tokens(value: object) -> tuple[NameToken, ...]:
    """Keep exact native tokens; reject initials, titles, digits and mixed scripts.

    Source offsets and diacritics remain intact. The parser supplies normalized
    Unicode; this tokenizer does not merge Urdu letter variants or infer Latin.
    """
    return tuple(
        token
        for token in tokenize_name(value)
        if token.letter_count >= 2
        and token.normalized not in TITLES
        and all(arabic_character(char) for char in token.normalized)
    )
