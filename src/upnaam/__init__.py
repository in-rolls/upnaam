"""Surname resolution for parsed Indian electoral rolls."""

from upnaam.candidates import SurnameCandidateResult, extract_surname_candidates
from upnaam.normalization import (
    NORMALIZATION_REVISION,
    NameToken,
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

__all__ = [
    "ELECTOR_INPUT_COLUMNS",
    "ELECTOR_OUTPUT_COLUMNS",
    "NORMALIZATION_REVISION",
    "NameToken",
    "ResolverPolicy",
    "SurnameCandidateResult",
    "extract_surname_candidates",
    "load_default_resolver_policy",
    "load_resolver_policy",
    "normalize_name",
    "resolve_electors",
    "tokenize_name",
]
