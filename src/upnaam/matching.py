"""Reproducible string comparisons, distinct from surname confidence."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Literal

import rapidfuzz
from rapidfuzz.distance import JaroWinkler, Levenshtein

MATCHING_REVISION = "string-matching-v1"


@dataclass(frozen=True, slots=True)
class MatchPolicy:
    """An explicit metric, threshold and revision on already normalized strings."""

    metric: Literal["exact", "levenshtein_distance", "jaro_winkler_similarity"]
    threshold: float
    revision: str
    prefix_weight: float = 0.1

    def __post_init__(self) -> None:
        """Reject policies whose scores or parameters would be uninterpretable."""
        if not self.revision.strip():
            raise ValueError("matching revision must be nonempty")
        if not math.isfinite(self.threshold):
            raise ValueError("matching threshold must be finite")
        if self.metric == "exact":
            if self.threshold != 1:
                raise ValueError("exact matching requires threshold 1")
        elif self.metric == "levenshtein_distance":
            if self.threshold < 0 or self.threshold != int(self.threshold):
                raise ValueError("Levenshtein threshold must be a nonnegative integer")
        elif self.metric == "jaro_winkler_similarity":
            if not 0 <= self.threshold <= 1:
                raise ValueError("Jaro-Winkler threshold must be between zero and one")
        else:
            raise ValueError("unsupported matching metric")
        if not math.isfinite(self.prefix_weight) or not 0 <= self.prefix_weight <= 0.25:
            raise ValueError("prefix_weight must be between zero and 0.25")


def compare_strings(left: str, right: str, policy: MatchPolicy) -> dict[str, object]:
    """Evaluate a comparison and retain the uncensored score and exact parameters.

    Args:
        left: Nonempty, already normalized comparison string.
        right: Nonempty, already normalized comparison string.
        policy: Metric-specific acceptance policy.

    Returns:
        Serializable evidence including rejected scores. No accuracy is inferred.

    Raises:
        ValueError: A comparison string is empty.
    """
    if not left or not right:
        raise ValueError("comparison strings must be nonempty")
    operations = None
    if policy.metric == "exact":
        score = float(left == right)
        accepted = left == right
        parameters = {}
    elif policy.metric == "levenshtein_distance":
        score = float(Levenshtein.distance(left, right))
        accepted = score <= policy.threshold
        parameters = {"weights": [1, 1, 1], "processor": None, "score_cutoff": None}
        operations = json.dumps(Levenshtein.editops(left, right).as_list())
    else:
        score = JaroWinkler.similarity(left, right, prefix_weight=policy.prefix_weight)
        accepted = score >= policy.threshold
        parameters = {
            "prefix_weight": policy.prefix_weight,
            "processor": None,
            "score_cutoff": None,
        }
    return {
        "left_value": left,
        "right_value": right,
        "metric": policy.metric,
        "metric_value": score,
        "threshold": policy.threshold,
        "parameters": json.dumps(parameters, sort_keys=True),
        "edit_operations": operations,
        "metric_revision": f"rapidfuzz:{rapidfuzz.__version__}",
        "matching_revision": policy.revision,
        "accepted": accepted,
        "reason_code": "within_threshold" if accepted else "outside_threshold",
    }
