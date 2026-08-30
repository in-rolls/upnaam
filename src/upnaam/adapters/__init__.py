"""Source adapters that produce standard Upnaam surname records."""

from upnaam.adapters.bihar import build_bihar_land_reference_labels
from upnaam.adapters.bihar_land_counts import build_bihar_land_surname_counts
from upnaam.adapters.bihar_land_inference import infer_bihar_land_surname_counts
from upnaam.adapters.bihar_ration import build_bihar_ration_surname_counts
from upnaam.adapters.punjab import build_punjab_elector_artifact
from upnaam.adapters.rajasthan import build_rajasthan_surname_evidence
from upnaam.adapters.rajasthan_reference import (
    build_rajasthan_ration_reference_labels,
)

__all__ = [
    "build_bihar_land_reference_labels",
    "build_bihar_land_surname_counts",
    "build_bihar_ration_surname_counts",
    "build_punjab_elector_artifact",
    "build_rajasthan_ration_reference_labels",
    "build_rajasthan_surname_evidence",
    "infer_bihar_land_surname_counts",
]
