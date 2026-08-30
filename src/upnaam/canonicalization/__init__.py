"""Evidence-backed canonicalization of normalized surname spellings."""

from upnaam.canonicalization.alignment import TokenAlignment, align_names
from upnaam.canonicalization.candidates import (
    VariantCandidate,
    generate_variant_candidates,
)
from upnaam.canonicalization.clustering import VariantMapping, cluster_variants
from upnaam.canonicalization.edits import (
    CharacterEdit,
    character_edits,
    summarize_edits,
)
from upnaam.canonicalization.evidence import EvidenceTier, VariantEvidence
from upnaam.canonicalization.mapping import (
    apply_canonical_map,
    canonical_map_from_frame,
)

__all__ = [
    "CharacterEdit",
    "EvidenceTier",
    "TokenAlignment",
    "VariantCandidate",
    "VariantEvidence",
    "VariantMapping",
    "align_names",
    "apply_canonical_map",
    "canonical_map_from_frame",
    "character_edits",
    "cluster_variants",
    "generate_variant_candidates",
    "summarize_edits",
]
