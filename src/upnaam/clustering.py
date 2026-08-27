"""Conservative, evidence-backed spelling-variant clustering."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class VariantEvidence:
    """Aggregated evidence that two observed tokens are variants."""

    left: str
    right: str
    support: int
    similarity: float
    source: str


@dataclass(frozen=True, slots=True)
class VariantMapping:
    """One variant-to-canonical assignment."""

    variant: str
    canonical: str
    cluster_size: int
    direct_support: int
    sources: tuple[str, ...]


def _medoid_key(
    token: str,
    *,
    members: frozenset[str],
    direct: dict[frozenset[str], VariantEvidence],
    frequency: Counter[str],
) -> tuple[float, int, str]:
    distance = sum(
        1 - direct[frozenset((token, other))].similarity
        for other in members
        if other != token
    )
    return (distance, -frequency[token], token)


def cluster_variants(
    evidence: Iterable[VariantEvidence],
    *,
    min_support: int = 2,
    min_similarity: float = 0.75,
) -> tuple[VariantMapping, ...]:
    """Cluster tokens only when every cross-cluster pair has direct evidence.

    Args:
        evidence: Aggregated linked-pair evidence.
        min_support: Minimum accepted links for a direct compatibility edge.
        min_similarity: Minimum normalized Levenshtein similarity.

    Returns:
        Deterministic mappings. Complete-link compatibility prevents a chain
        of weak pairwise similarities from collapsing unrelated tokens.

    Raises:
        ValueError: If thresholds are outside their valid ranges.
    """
    if min_support < 1:
        raise ValueError("min_support must be at least one")
    if not 0 <= min_similarity <= 1:
        raise ValueError("min_similarity must be between zero and one")
    accepted = [
        item
        for item in evidence
        if item.left != item.right
        and item.support >= min_support
        and item.similarity >= min_similarity
    ]
    direct: dict[frozenset[str], VariantEvidence] = {}
    frequency: Counter[str] = Counter()
    token_sources: defaultdict[str, set[str]] = defaultdict(set)
    for item in accepted:
        key = frozenset((item.left, item.right))
        previous = direct.get(key)
        if previous is None or (item.support, item.similarity) > (
            previous.support,
            previous.similarity,
        ):
            direct[key] = item
        frequency[item.left] += item.support
        frequency[item.right] += item.support
        token_sources[item.left].add(item.source)
        token_sources[item.right].add(item.source)
    clusters: list[set[str]] = [{token} for token in sorted(frequency)]
    for item in sorted(
        direct.values(),
        key=lambda value: (-value.support, -value.similarity, value.left, value.right),
    ):
        left_cluster = next(group for group in clusters if item.left in group)
        right_cluster = next(group for group in clusters if item.right in group)
        if left_cluster is right_cluster:
            continue
        if all(
            frozenset((left, right)) in direct
            for left in left_cluster
            for right in right_cluster
        ):
            left_cluster.update(right_cluster)
            clusters.remove(right_cluster)

    mappings: list[VariantMapping] = []
    for cluster in clusters:
        members = frozenset(cluster)
        medoid_key = partial(
            _medoid_key, members=members, direct=direct, frequency=frequency
        )
        canonical = min(cluster, key=medoid_key)
        for token in sorted(cluster):
            support = sum(
                direct[frozenset((token, other))].support
                for other in cluster
                if other != token and frozenset((token, other)) in direct
            )
            mappings.append(
                VariantMapping(
                    variant=token,
                    canonical=canonical,
                    cluster_size=len(cluster),
                    direct_support=support,
                    sources=tuple(sorted(token_sources[token])),
                )
            )
    return tuple(mappings)
