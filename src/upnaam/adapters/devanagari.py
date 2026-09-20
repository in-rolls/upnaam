"""Conservative native Devanagari evidence without Latin transliteration."""

from __future__ import annotations

import unicodedata

from upnaam.normalization import NameToken, tokenize_name

TITLES = frozenset({"श्री", "श्रीमती", "सुश्री", "स्वर्गीय", "स्व", "डा", "डॉ"})


def devanagari_character(char: str) -> bool:
    """Return whether a character is a Devanagari letter or combining mark."""
    return "\u0900" <= char <= "\u097f" and unicodedata.category(char)[0] in "LM"


def devanagari_tokens(value: object) -> tuple[NameToken, ...]:
    """Retain native tokens and marks; reject initials, titles and mixed scripts.

    Two letters suffice: vowel signs are marks, so the Latin three-letter rule
    would exclude written tokens such as राम. Punctuation is retained in the
    source but cannot supply evidence. Formatting marks follow normalize_name.
    """
    return tuple(
        token
        for token in tokenize_name(value)
        if token.letter_count >= 2
        and token.normalized not in TITLES
        and all(devanagari_character(char) for char in token.normalized)
    )
