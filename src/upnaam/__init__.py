"""Surname resolution for parsed Indian electoral rolls."""

from upnaam.normalization import (
    NORMALIZATION_REVISION,
    NameToken,
    normalize_latin_token,
    normalize_name,
    tokenize_name,
)
from upnaam.policy import (
    ResolverPolicy,
    load_default_resolver_policy,
    load_resolver_policy,
)
from upnaam.resolver import (
    ELECTOR_INPUT_COLUMNS,
    ELECTOR_OUTPUT_COLUMNS,
    resolve_electors,
)
from upnaam.schema import CANONICALIZATION_REVISION, CanonicalizationStatus
from upnaam.selection import SurnameCandidateResult, extract_surname_candidates

__all__ = [
    "CANONICALIZATION_REVISION",
    "ELECTOR_INPUT_COLUMNS",
    "ELECTOR_OUTPUT_COLUMNS",
    "NORMALIZATION_REVISION",
    "CanonicalizationStatus",
    "NameToken",
    "ResolverPolicy",
    "SurnameCandidateResult",
    "extract_surname_candidates",
    "load_default_resolver_policy",
    "load_resolver_policy",
    "normalize_latin_token",
    "normalize_name",
    "resolve_electors",
    "tokenize_name",
]
