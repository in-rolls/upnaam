"""Surname resolution for parsed Indian electoral rolls."""

from upnaam.candidates import SurnameCandidateResult, extract_surname_candidates
from upnaam.normalization import NameToken, normalize_name, tokenize_name

__all__ = [
    "NameToken",
    "SurnameCandidateResult",
    "extract_surname_candidates",
    "normalize_name",
    "tokenize_name",
]
