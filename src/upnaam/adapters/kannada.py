"""Aligned Kannada token romanization for surname evidence."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from upnaam.corroboration import content_tokens
from upnaam.normalization import NameToken, normalize_name

if TYPE_CHECKING:
    from collections.abc import Callable

_WORD = re.compile(r"[A-Za-z]+|[\u0c80-\u0cff\u200c\u200d]+")
INITIALS = frozenset(
    [
        "ಎ",
        "ಬಿ",
        "ಸಿ",
        "ಡಿ",
        "ಇ",
        "ಈ",
        "ಎಫ್",
        "ಜಿ",
        "ಎಚ್",
        "ಹೆಚ್",
        "ಐ",
        "ಜೆ",
        "ಜೇ",
        "ಕೆ",
        "ಕೇ",
        "ಎಲ್",
        "ಎಂ",
        "ಎಮ್",
        "ಎನ್",
        "ಒ",
        "ಓ",
        "ಪಿ",
        "ಕ್ಯೂ",
        "ಆರ್",
        "ಅರ್",
        "ಎಸ್",
        "ಎಸ",
        "ಯಂ",
        "ಟಿ",
        "ಯು",
        "ಯೂ",
        "ವಿ",
        "ಡಬ್ಲ್ಯೂ",
        "ಡಬ್ಲ್ಯು",
        "ಡಬ್ಲು",
        "ಎಕ್ಸ್",
        "ವೈ",
        "ಝೆಡ್",
        "ಜೆಡ್",
        "ಜಡ್",
        "ಜೇಡ್",
    ]
)

_INITIAL_SEQUENCE = re.compile(
    "(?:" + "|".join(re.escape(word) for word in sorted(INITIALS)) + "){2,}"
)


def _source_words(value: object) -> tuple[tuple[str, int, int], ...]:
    if not isinstance(value, str):
        return ()
    words = []
    for segment in re.finditer(r"\S+", value):
        text = segment.group()
        if "\ufffd" in text:
            continue
        for match in _WORD.finditer(text):
            if (match.start() and text[match.start() - 1].isalnum()) or (
                match.end() < len(text) and text[match.end()].isalnum()
            ):
                continue
            raw = match.group()
            normalized = normalize_name(raw)
            if (
                normalized in INITIALS
                or len(raw) == 1
                or (normalized is not None and _INITIAL_SEQUENCE.fullmatch(normalized))
            ):
                continue
            words.append(
                (raw, segment.start() + match.start(), segment.start() + match.end())
            )
    return tuple(words)


class KannadaEvidenceTokens:
    """Romanize eligible source tokens without inventing a complete Latin name."""

    def __init__(self, romanize: Callable[[str], str | None]) -> None:
        """Use a local, non-generative token lookup."""
        self.romanize = romanize

    def has_multiple_words(self, value: object) -> bool:
        """Require two written content words; unknown words still count."""
        count = 0
        for raw, _, _ in _source_words(value):
            latin = raw if raw.isascii() else self.romanize(raw)
            if latin is not None and not content_tokens(latin):
                continue
            count += 1
        return count >= 2

    def __call__(self, value: object) -> tuple[NameToken, ...]:
        """Preserve source spans and reject initials before romanization."""
        result = []
        for raw, start, end in _source_words(value):
            latin = raw if raw.isascii() else self.romanize(raw)
            if not latin or not latin.isascii() or len(latin.split()) != 1:
                continue
            eligible = content_tokens(latin)
            if len(eligible) != 1:
                continue
            token = eligible[0]
            result.append(
                NameToken(
                    raw=raw,
                    normalized=token.normalized,
                    start=start,
                    end=end,
                    letter_count=token.letter_count,
                )
            )
        return tuple(result)

    def initials_candidate(self, value: object) -> NameToken | None:
        """Return the sole usable word beside explicit, undamaged initials."""
        if not isinstance(value, str) or "\ufffd" in value:
            return None
        if any(char.isdigit() for char in value):
            return None
        if any(
            char.isalpha() and not (char.isascii() or "\u0c80" <= char <= "\u0cff")
            for char in value
        ):
            return None
        initials = words = 0
        for segment in re.finditer(r"\S+", value):
            text = segment.group()
            for match in _WORD.finditer(text):
                if (match.start() and text[match.start() - 1].isalnum()) or (
                    match.end() < len(text) and text[match.end()].isalnum()
                ):
                    return None
                raw = match.group()
                normalized = normalize_name(raw)
                if len(raw) == 1:
                    if not raw.isalpha():
                        return None
                    initials += 1
                elif normalized in INITIALS:
                    initials += 1
                elif normalized and _INITIAL_SEQUENCE.fullmatch(normalized):
                    return None
                else:
                    words += 1
        if not initials or words != 1:
            return None
        tokens = self(value)
        return tokens[0] if len(tokens) == 1 else None
