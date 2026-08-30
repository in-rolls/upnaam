"""Candidate generation for similar normalized surname spellings."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

from rapidfuzz.distance import Levenshtein

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class VariantCandidate:
    """One string-similarity candidate that has not been declared equivalent."""

    left: str
    right: str
    distance: int
    similarity: float
    left_frequency: int
    right_frequency: int


def _deletion_signatures(token: str, max_distance: int) -> set[str]:
    signatures = {token}
    frontier = {token}
    for _ in range(max_distance):
        next_frontier = {
            value[:index] + value[index + 1 :]
            for value in frontier
            for index in range(len(value))
            if value
        }
        signatures.update(next_frontier)
        frontier = next_frontier
    return signatures


def generate_variant_candidates(
    frequencies: Mapping[str, int] | Iterable[tuple[str, int]],
    *,
    max_distance: int = 2,
    min_similarity: float = 0.75,
) -> tuple[VariantCandidate, ...]:
    """Generate plausible edit-distance pairs without accepting any merge.

    Args:
        frequencies: Normalized surname tokens and observed record counts.
        max_distance: Maximum ordinary Levenshtein distance.
        min_similarity: Minimum normalized Levenshtein similarity.

    Returns:
        Deterministic candidate pairs. Sharing a deletion signature is only a
        blocking device; every emitted pair is checked with exact distance.

    Raises:
        ValueError: If counts or thresholds are invalid.
    """
    if max_distance < 1:
        raise ValueError("max_distance must be at least one")
    if not 0 <= min_similarity <= 1:
        raise ValueError("min_similarity must be between zero and one")
    items: defaultdict[str, int] = defaultdict(int)
    if isinstance(frequencies, Mapping):
        items.update(frequencies)
    else:
        for token, count in frequencies:
            items[token] += count
    if any(
        not isinstance(token, str) or not token or count < 1
        for token, count in items.items()
    ):
        raise ValueError("surname tokens must be nonempty with positive counts")
    blocks: defaultdict[str, list[str]] = defaultdict(list)
    for token in sorted(items):
        for signature in _deletion_signatures(token, max_distance):
            blocks[signature].append(token)
    pairs: set[tuple[str, str]] = set()
    for members in blocks.values():
        if len(members) < 2:
            continue
        pairs.update(combinations(sorted(set(members)), 2))
    output: list[VariantCandidate] = []
    for left, right in sorted(pairs):
        distance = Levenshtein.distance(left, right)
        similarity = 1 - Levenshtein.normalized_distance(left, right)
        if distance <= max_distance and similarity >= min_similarity:
            output.append(
                VariantCandidate(
                    left=left,
                    right=right,
                    distance=distance,
                    similarity=similarity,
                    left_frequency=items[left],
                    right_frequency=items[right],
                )
            )
    return tuple(output)
