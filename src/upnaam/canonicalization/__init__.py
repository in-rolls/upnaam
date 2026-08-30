"""Candidate generation and anchored surname reconciliation."""

from upnaam.canonicalization.alignment import TokenAlignment, align_names
from upnaam.canonicalization.candidates import (
    VARIANT_CANDIDATE_REVISION,
    VariantCandidate,
    generate_variant_candidates,
)
from upnaam.canonicalization.edits import (
    CharacterEdit,
    character_edits,
    summarize_edits,
)
from upnaam.canonicalization.mapping import (
    AppliedDecision,
    apply_reconciliation,
    reconciliation_index_from_frame,
)
from upnaam.canonicalization.reconciliation import (
    RECONCILIATION_REVISION,
    AnchorEvidence,
    RankedAnchorCandidate,
    ReconciliationDecision,
    ReconciliationStatus,
    decide_anchor_candidates,
    rank_anchor_candidates,
)

__all__ = [
    "RECONCILIATION_REVISION",
    "VARIANT_CANDIDATE_REVISION",
    "AnchorEvidence",
    "AppliedDecision",
    "CharacterEdit",
    "RankedAnchorCandidate",
    "ReconciliationDecision",
    "ReconciliationStatus",
    "TokenAlignment",
    "VariantCandidate",
    "align_names",
    "apply_reconciliation",
    "character_edits",
    "decide_anchor_candidates",
    "generate_variant_candidates",
    "rank_anchor_candidates",
    "reconciliation_index_from_frame",
    "summarize_edits",
]
