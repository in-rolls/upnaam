"""Anchored surname reconciliation with explicit ambiguity."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


RECONCILIATION_REVISION = "reconciliation-v1"


class ReconciliationStatus(StrEnum):
    """Outcome of reconciling one observed form in one context."""

    ACCEPTED = "accepted"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class AnchorEvidence:
    """Directed evidence from an observed form to a canonical anchor."""

    observed_form: str
    context: str
    canonical_id: str
    canonical_label: str
    support: int
    similarity: float
    source: str
    evidence_tier: str

    def __post_init__(self) -> None:
        """Reject malformed directed evidence."""
        strings = (
            self.observed_form,
            self.context,
            self.canonical_id,
            self.canonical_label,
            self.source,
            self.evidence_tier,
        )
        if any(not value for value in strings):
            raise ValueError("anchor evidence strings must be nonempty")
        if self.support < 1:
            raise ValueError("anchor evidence support must be at least one")
        if not 0 <= self.similarity <= 1:
            raise ValueError("anchor evidence similarity must be between zero and one")


@dataclass(frozen=True, slots=True)
class RankedAnchorCandidate:
    """One aggregated and ranked canonical candidate."""

    observed_form: str
    context: str
    canonical_id: str
    canonical_label: str
    rank: int
    eligible: bool
    support: int
    total_support: int
    support_share: float
    weighted_similarity: float
    sources: tuple[str, ...]
    evidence_tiers: tuple[str, ...]
    min_support_threshold: int
    min_similarity_threshold: float
    reconciliation_revision: str = RECONCILIATION_REVISION

    def __post_init__(self) -> None:
        """Reject candidate rows that cannot be interpreted consistently."""
        strings = (
            self.observed_form,
            self.context,
            self.canonical_id,
            self.canonical_label,
            self.reconciliation_revision,
        )
        if any(not value for value in strings):
            raise ValueError("ranked candidate strings must be nonempty")
        if self.rank < 1:
            raise ValueError("candidate rank must be at least one")
        if self.support < 1 or self.total_support < self.support:
            raise ValueError("candidate support totals are invalid")
        if not 0 < self.support_share <= 1:
            raise ValueError(
                "candidate support share must be above zero and at most one"
            )
        if not 0 <= self.weighted_similarity <= 1:
            raise ValueError("candidate similarity must be between zero and one")
        if not self.sources or not self.evidence_tiers:
            raise ValueError("candidate evidence provenance must be nonempty")
        if self.min_support_threshold < 1:
            raise ValueError("candidate support threshold must be at least one")
        if not 0 <= self.min_similarity_threshold <= 1:
            raise ValueError(
                "candidate similarity threshold must be between zero and one"
            )
        expected_eligibility = (
            self.support >= self.min_support_threshold
            and self.weighted_similarity >= self.min_similarity_threshold
        )
        if self.eligible is not expected_eligibility:
            raise ValueError("candidate eligibility does not match its thresholds")


@dataclass(frozen=True, slots=True)
class ReconciliationDecision:
    """One non-probabilistic reconciliation decision."""

    observed_form: str
    context: str
    canonical_id: str | None
    canonical_label: str | None
    status: ReconciliationStatus
    reason: str
    candidate_count: int
    eligible_candidate_count: int
    top_support: int | None
    runner_up_support: int | None
    min_support_threshold: int
    min_similarity_threshold: float
    reconciliation_revision: str = RECONCILIATION_REVISION


@dataclass(slots=True)
class _Aggregate:
    support: int = 0
    weighted_similarity: float = 0
    sources: set[str] | None = None
    tiers: set[str] | None = None

    def add(self, item: AnchorEvidence) -> None:
        """Add one evidence row to the aggregate."""
        self.support += item.support
        self.weighted_similarity += item.similarity * item.support
        if self.sources is None:
            self.sources = set()
        if self.tiers is None:
            self.tiers = set()
        self.sources.add(item.source)
        self.tiers.add(item.evidence_tier)


def rank_anchor_candidates(
    evidence: Iterable[AnchorEvidence],
    *,
    min_support: int = 2,
    min_similarity: float = 0.75,
) -> tuple[RankedAnchorCandidate, ...]:
    """Aggregate and rank directed candidates without forcing a decision.

    Args:
        evidence: Directed observations and their proposed anchors.
        min_support: Minimum aggregate support for decision eligibility.
        min_similarity: Minimum support-weighted string similarity.

    Returns:
        All observed candidates, including ineligible candidates, ranked within
        each observed-form and context pair. ``support_share`` is descriptive;
        it is not a calibrated probability.

    Raises:
        ValueError: If thresholds are invalid or an anchor ID has conflicting
            labels.
    """
    if min_support < 1:
        raise ValueError("min_support must be at least one")
    if not 0 <= min_similarity <= 1:
        raise ValueError("min_similarity must be between zero and one")
    labels: dict[str, str] = {}
    grouped: defaultdict[tuple[str, str, str], _Aggregate] = defaultdict(_Aggregate)
    for item in evidence:
        previous_label = labels.setdefault(item.canonical_id, item.canonical_label)
        if previous_label != item.canonical_label:
            raise ValueError(
                f"canonical anchor has conflicting labels: {item.canonical_id}"
            )
        grouped[(item.observed_form, item.context, item.canonical_id)].add(item)

    by_observed: defaultdict[tuple[str, str], list[tuple[str, _Aggregate]]] = (
        defaultdict(list)
    )
    for (observed_form, context, canonical_id), aggregate in grouped.items():
        by_observed[(observed_form, context)].append((canonical_id, aggregate))

    output: list[RankedAnchorCandidate] = []
    for (observed_form, context), candidates in sorted(by_observed.items()):
        total_support = sum(aggregate.support for _, aggregate in candidates)

        def candidate_key(item: tuple[str, _Aggregate]) -> tuple[bool, int, float, str]:
            canonical_id, aggregate = item
            similarity = aggregate.weighted_similarity / aggregate.support
            eligible = aggregate.support >= min_support and similarity >= min_similarity
            return (not eligible, -aggregate.support, -similarity, canonical_id)

        for rank, (canonical_id, aggregate) in enumerate(
            sorted(candidates, key=candidate_key), start=1
        ):
            similarity = aggregate.weighted_similarity / aggregate.support
            output.append(
                RankedAnchorCandidate(
                    observed_form=observed_form,
                    context=context,
                    canonical_id=canonical_id,
                    canonical_label=labels[canonical_id],
                    rank=rank,
                    eligible=(
                        aggregate.support >= min_support
                        and similarity >= min_similarity
                    ),
                    support=aggregate.support,
                    total_support=total_support,
                    support_share=aggregate.support / total_support,
                    weighted_similarity=similarity,
                    sources=tuple(sorted(aggregate.sources or ())),
                    evidence_tiers=tuple(sorted(aggregate.tiers or ())),
                    min_support_threshold=min_support,
                    min_similarity_threshold=min_similarity,
                )
            )
    return tuple(output)


def decide_anchor_candidates(
    candidates: Iterable[RankedAnchorCandidate],
) -> tuple[ReconciliationDecision, ...]:
    """Accept one supported anchor, preserve forks, or remain unresolved.

    Args:
        candidates: Ranked candidate rows from one reconciliation revision.

    Returns:
        One decision per observed-form and context pair. A decision is accepted
        only when exactly one candidate is eligible. No support margin is
        interpreted as calibrated evidence in this revision.

    Raises:
        ValueError: If candidates contain duplicate ranks, conflicting labels,
            or multiple reconciliation revisions.
    """
    grouped: defaultdict[tuple[str, str], list[RankedAnchorCandidate]] = defaultdict(
        list
    )
    revisions: set[str] = set()
    artifact_thresholds: set[tuple[int, float]] = set()
    labels: dict[str, str] = {}
    for item in candidates:
        revisions.add(item.reconciliation_revision)
        artifact_thresholds.add(
            (item.min_support_threshold, item.min_similarity_threshold)
        )
        previous_label = labels.setdefault(item.canonical_id, item.canonical_label)
        if previous_label != item.canonical_label:
            raise ValueError(
                f"canonical anchor has conflicting labels: {item.canonical_id}"
            )
        grouped[(item.observed_form, item.context)].append(item)
    if len(revisions) > 1:
        raise ValueError("candidate table contains multiple reconciliation revisions")
    if len(artifact_thresholds) > 1:
        raise ValueError("candidate table contains multiple threshold configurations")

    decisions: list[ReconciliationDecision] = []
    for (observed_form, context), group in sorted(grouped.items()):
        ranks = [item.rank for item in group]
        if sorted(ranks) != list(range(1, len(group) + 1)):
            raise ValueError(
                "candidate ranks must be consecutive within an observation"
            )
        totals = {item.total_support for item in group}
        if len(totals) != 1 or totals.pop() != sum(item.support for item in group):
            raise ValueError("candidate total support is inconsistent")
        thresholds = {
            (item.min_support_threshold, item.min_similarity_threshold)
            for item in group
        }
        if len(thresholds) != 1:
            raise ValueError("candidate thresholds are inconsistent")
        min_support, min_similarity = thresholds.pop()
        ordered = sorted(group, key=lambda item: item.rank)
        eligible = [item for item in ordered if item.eligible]
        if len(eligible) == 1:
            winner = eligible[0]
            status = ReconciliationStatus.ACCEPTED
            reason = "single_supported_anchor"
            canonical_id = winner.canonical_id
            canonical_label = winner.canonical_label
        elif eligible:
            status = ReconciliationStatus.AMBIGUOUS
            reason = "multiple_supported_anchors"
            canonical_id = None
            canonical_label = None
        else:
            status = ReconciliationStatus.UNRESOLVED
            reason = "no_supported_anchor"
            canonical_id = None
            canonical_label = None
        decisions.append(
            ReconciliationDecision(
                observed_form=observed_form,
                context=context,
                canonical_id=canonical_id,
                canonical_label=canonical_label,
                status=status,
                reason=reason,
                candidate_count=len(ordered),
                eligible_candidate_count=len(eligible),
                top_support=ordered[0].support if ordered else None,
                runner_up_support=ordered[1].support if len(ordered) > 1 else None,
                min_support_threshold=min_support,
                min_similarity_threshold=min_similarity,
                reconciliation_revision=(
                    ordered[0].reconciliation_revision
                    if ordered
                    else RECONCILIATION_REVISION
                ),
            )
        )
    return tuple(decisions)
