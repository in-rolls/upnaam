"""Source adapters that produce standard Upnaam surname records."""

from upnaam.adapters.bihar import build_bihar_land_reference_labels
from upnaam.adapters.punjab import build_punjab_elector_artifact
from upnaam.adapters.rajasthan import build_rajasthan_surname_evidence

__all__ = [
    "build_bihar_land_reference_labels",
    "build_punjab_elector_artifact",
    "build_rajasthan_surname_evidence",
]
