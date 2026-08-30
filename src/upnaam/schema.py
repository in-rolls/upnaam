"""Stable field names and statuses for surname artifacts."""

from __future__ import annotations

from enum import StrEnum

CANONICALIZATION_REVISION = "reconciliation-v1"


class CanonicalizationStatus(StrEnum):
    """State of a normalized surname's canonicalization."""

    IDENTITY_UNMAPPED = "identity_unmapped"
    CANONICAL_IDENTITY = "canonical_identity"
    VARIANT_MAPPED = "variant_mapped"
    AMBIGUOUS = "ambiguous"
    NORMALIZATION_UNAVAILABLE = "normalization_unavailable"
    NOT_APPLICABLE = "not_applicable"


SURNAME_REPRESENTATION_COLUMNS = (
    "surname_raw",
    "surname_source_normalized",
    "surname_latin_raw",
    "surname_latin_normalized",
    "surname_canonical",
    "canonicalization_status",
    "canonicalization_reason",
    "canonicalization_provenance",
    "canonicalization_revision",
)

SURNAME_SELECTION_COLUMNS = (
    "surname_position",
    "surname_provenance",
    "abstained",
    "abstention_reason",
    "normalization_revision",
    "resolver_revision",
)
