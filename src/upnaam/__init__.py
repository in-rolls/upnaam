"""Surname resolution for parsed Indian electoral rolls."""

from upnaam.candidates import SurnameCandidateResult, extract_surname_candidates
from upnaam.normalization import NameToken, normalize_name, tokenize_name
from upnaam.policy import ResolverPolicy, load_resolver_policy

__all__ = [
    "NameToken",
    "ResolverPolicy",
    "SurnameCandidateResult",
    "extract_surname_candidates",
    "load_resolver_policy",
    "normalize_name",
    "tokenize_name",
]
