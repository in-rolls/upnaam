"""Typed evidence for possible and accepted surname variants."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EvidenceTier(StrEnum):
    """Strength and origin of a surname-variant claim."""

    DETERMINISTIC = "deterministic_normalization"
    LINKED_RECORD = "linked_record"
    CROSS_YEAR = "cross_year"
    CONTEXTUAL = "contextual"
    STRING_ONLY = "string_only"


@dataclass(frozen=True, slots=True)
class VariantEvidence:
    """Aggregated evidence relating two normalized surname spellings."""

    left: str
    right: str
    support: int
    similarity: float
    source: str
    evidence_tier: EvidenceTier = EvidenceTier.LINKED_RECORD
    accepted: bool = True
    preferred: str | None = None

    def __post_init__(self) -> None:
        """Reject malformed or internally inconsistent evidence."""
        if not self.left or not self.right:
            raise ValueError("variant evidence tokens must be nonempty")
        if self.support < 1:
            raise ValueError("variant evidence support must be at least one")
        if not 0 <= self.similarity <= 1:
            raise ValueError("variant evidence similarity must be between zero and one")
        if self.preferred not in {None, self.left, self.right}:
            raise ValueError("preferred spelling must be one of the evidence tokens")

    @property
    def pair(self) -> frozenset[str]:
        """Return the unordered token pair represented by this evidence."""
        return frozenset((self.left, self.right))
