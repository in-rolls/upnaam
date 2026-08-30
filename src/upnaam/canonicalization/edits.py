"""Observed character edits in accepted linked name pairs."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

from rapidfuzz.distance import Levenshtein


@dataclass(frozen=True, slots=True)
class CharacterEdit:
    """One character edit observed within an aligned token pair."""

    operation: str
    roll_character: str
    external_character: str


def character_edits(roll_token: str, external_token: str) -> tuple[CharacterEdit, ...]:
    """Return the minimum Levenshtein edit operations for two tokens.

    Args:
        roll_token: Normalized electoral-roll token.
        external_token: Normalized linked-source token.

    Returns:
        Ordered insertions, deletions, and substitutions.
    """
    edits: list[CharacterEdit] = []
    for operation in Levenshtein.editops(roll_token, external_token):
        roll_character = (
            roll_token[operation.src_pos]
            if operation.tag in {"delete", "replace"}
            else ""
        )
        external_character = (
            external_token[operation.dest_pos]
            if operation.tag in {"insert", "replace"}
            else ""
        )
        edits.append(CharacterEdit(operation.tag, roll_character, external_character))
    return tuple(edits)


def summarize_edits(
    token_pairs: Iterable[tuple[str, str]],
) -> dict[str, object]:
    """Count observed edit operations without treating counts as probabilities.

    Args:
        token_pairs: Normalized roll and external token pairs.

    Returns:
        Pair and operation counts suitable for a versioned JSON artifact.
    """
    pair_counts: Counter[tuple[str, str]] = Counter()
    edit_counts: Counter[CharacterEdit] = Counter()
    for roll_token, external_token in token_pairs:
        pair_counts[(roll_token, external_token)] += 1
        edit_counts.update(character_edits(roll_token, external_token))
    return {
        "substitution_pairs": sum(pair_counts.values()),
        "unique_substitution_pairs": len(pair_counts),
        "pairs": [
            {"roll_token": left, "external_token": right, "count": count}
            for (left, right), count in sorted(
                pair_counts.items(), key=lambda item: (-item[1], item[0])
            )
        ],
        "edits": [
            {**asdict(edit), "count": count}
            for edit, count in sorted(
                edit_counts.items(),
                key=lambda item: (
                    -item[1],
                    item[0].operation,
                    item[0].roll_character,
                    item[0].external_character,
                ),
            )
        ],
    }
