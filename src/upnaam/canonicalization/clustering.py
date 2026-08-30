"""Conservative, evidence-backed spelling-variant clustering."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from upnaam.canonicalization.evidence import EvidenceTier, VariantEvidence

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class VariantMapping:
    """One variant-to-canonical assignment."""

    variant: str
    canonical: str
    cluster_size: int
    direct_support: int
    sources: tuple[str, ...]
    evidence_tiers: tuple[str, ...]


def _canonical_key(
    token: str,
    *,
    members: frozenset[str],
    direct: dict[frozenset[str], VariantEvidence],
    frequencies: Mapping[str, int],
    preference: Counter[str],
) -> tuple[int, float, int, str]:
    distance = sum(
        1 - direct[frozenset((token, other))].similarity
        for other in members
        if other != token
    )
    return (-preference[token], distance, -frequencies.get(token, 0), token)


def cluster_variants(
    evidence: Iterable[VariantEvidence],
    *,
    min_support: int = 2,
    min_similarity: float = 0.75,
    frequencies: Mapping[str, int] | None = None,
    allow_string_only: bool = False,
) -> tuple[VariantMapping, ...]:
    """Cluster tokens only when every cross-cluster pair has direct evidence.

    Args:
        evidence: Aggregated linked-pair evidence.
        min_support: Minimum accepted links for a direct compatibility edge.
        min_similarity: Minimum normalized Levenshtein similarity.
        frequencies: Optional corpus counts used only to break medoid ties.
        allow_string_only: Whether edit similarity alone may create edges.

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
        if item.accepted
        and item.left != item.right
        and item.support >= min_support
        and item.similarity >= min_similarity
        and (allow_string_only or item.evidence_tier is not EvidenceTier.STRING_ONLY)
    ]
    direct: dict[frozenset[str], VariantEvidence] = {}
    token_sources: defaultdict[str, set[str]] = defaultdict(set)
    token_tiers: defaultdict[str, set[str]] = defaultdict(set)
    preference: Counter[str] = Counter()
    for item in accepted:
        key = item.pair
        previous = direct.get(key)
        if previous is None or (item.support, item.similarity) > (
            previous.support,
            previous.similarity,
        ):
            direct[key] = item
        token_sources[item.left].add(item.source)
        token_sources[item.right].add(item.source)
        token_tiers[item.left].add(item.evidence_tier.value)
        token_tiers[item.right].add(item.evidence_tier.value)
        if item.preferred is not None:
            preference[item.preferred] += item.support
    tokens = sorted({token for item in accepted for token in (item.left, item.right)})
    clusters: list[set[str]] = [{token} for token in tokens]
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
        canonical = min(
            cluster,
            key=lambda token: _canonical_key(
                token,
                members=members,
                direct=direct,
                frequencies=frequencies or {},
                preference=preference,
            ),
        )
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
                    evidence_tiers=tuple(sorted(token_tiers[token])),
                )
            )
    return tuple(mappings)
