from dataclasses import replace

import pandas as pd
import pytest

from upnaam.canonicalization import (
    VARIANT_CANDIDATE_REVISION,
    AnchorEvidence,
    AppliedDecision,
    ReconciliationStatus,
    apply_reconciliation,
    decide_anchor_candidates,
    generate_variant_candidates,
    rank_anchor_candidates,
    reconciliation_index_from_frame,
)


def _evidence(
    observed: str,
    anchor: str,
    *,
    support: int = 3,
    similarity: float = 0.9,
    canonical_id: str | None = None,
) -> AnchorEvidence:
    return AnchorEvidence(
        observed_form=observed,
        context="rajasthan",
        canonical_id=canonical_id or f"anchor:{anchor}",
        canonical_label=anchor,
        support=support,
        similarity=similarity,
        source="ration:T2",
        evidence_tier="linked_record",
    )


def test_similarity_generates_candidates_without_declaring_a_mapping() -> None:
    candidates = generate_variant_candidates(
        {"jadhab": 12, "jadhav": 100, "sharma": 50}
    )
    assert [(item.left, item.right) for item in candidates] == [("jadhab", "jadhav")]
    assert candidates[0].candidate_reason == "edit_distance_gate"
    assert candidates[0].candidate_revision == VARIANT_CANDIDATE_REVISION


def test_candidate_blocking_does_not_drop_short_tokens() -> None:
    candidates = generate_variant_candidates(
        {"ra": 2, "rai": 3}, max_distance=1, min_similarity=0.6
    )
    assert [(item.left, item.right) for item in candidates] == [("ra", "rai")]


def test_reconciliation_accepts_exactly_one_supported_anchor() -> None:
    candidates = rank_anchor_candidates(
        [_evidence("jadhab", "jadhav"), _evidence("jadhab", "jadav", support=1)]
    )
    assert [candidate.rank for candidate in candidates] == [1, 2]
    assert [candidate.eligible for candidate in candidates] == [True, False]
    decision = decide_anchor_candidates(candidates)[0]
    assert decision.status is ReconciliationStatus.ACCEPTED
    assert decision.canonical_label == "jadhav"
    assert decision.reason == "single_supported_anchor"


def test_reconciliation_preserves_a_supported_fork_as_ambiguous() -> None:
    candidates = rank_anchor_candidates(
        [_evidence("sarma", "sharma"), _evidence("sarma", "sarma")]
    )
    decision = decide_anchor_candidates(candidates)[0]
    assert decision.status is ReconciliationStatus.AMBIGUOUS
    assert decision.canonical_label is None
    assert decision.eligible_candidate_count == 2
    assert decision.reason == "multiple_supported_anchors"


def test_reconciliation_keeps_weak_evidence_but_does_not_accept_it() -> None:
    candidates = rank_anchor_candidates([_evidence("rai", "ray", support=1)])
    assert not candidates[0].eligible
    decision = decide_anchor_candidates(candidates)[0]
    assert decision.status is ReconciliationStatus.UNRESOLVED
    assert decision.reason == "no_supported_anchor"


def test_apply_reconciliation_records_decision_and_nondecision_states() -> None:
    records = pd.DataFrame(
        {
            "surname_latin_normalized": [
                "jadhab",
                "jadhav",
                "sarma",
                "rai",
                "sharma",
                None,
                None,
            ],
            "abstained": [False, False, False, False, False, False, True],
        }
    )
    decisions = {
        ("jadhab", "global"): AppliedDecision(
            "jadhav", ReconciliationStatus.ACCEPTED, "single_supported_anchor", "v1"
        ),
        ("jadhav", "global"): AppliedDecision(
            "jadhav", ReconciliationStatus.ACCEPTED, "single_supported_anchor", "v1"
        ),
        ("sarma", "global"): AppliedDecision(
            None, ReconciliationStatus.AMBIGUOUS, "multiple_supported_anchors", "v1"
        ),
        ("rai", "global"): AppliedDecision(
            None, ReconciliationStatus.UNRESOLVED, "no_supported_anchor", "v1"
        ),
    }
    result = apply_reconciliation(records, decisions)
    assert result["surname_canonical"].tolist()[:2] == ["jadhav", "jadhav"]
    assert pd.isna(result.loc[2, "surname_canonical"])
    assert result.loc[3, "surname_canonical"] == "rai"
    assert result.loc[4, "surname_canonical"] == "sharma"
    assert result["canonicalization_status"].tolist() == [
        "variant_mapped",
        "canonical_identity",
        "ambiguous",
        "identity_unmapped",
        "identity_unmapped",
        "normalization_unavailable",
        "not_applicable",
    ]
    assert result["canonicalization_reason"].tolist()[:5] == [
        "single_supported_anchor",
        "single_supported_anchor",
        "multiple_supported_anchors",
        "no_supported_anchor",
        "no_reconciliation_decision",
    ]
    assert result.loc[0, "canonicalization_provenance"] == "anchored_reconciliation"
    assert pd.isna(result.loc[3, "canonicalization_provenance"])


def test_decision_loader_rejects_malformed_tables() -> None:
    valid = pd.DataFrame(
        {
            "observed_form": ["sarma"],
            "context": ["global"],
            "canonical_label": ["sharma"],
            "status": ["accepted"],
            "reason": ["single_supported_anchor"],
            "reconciliation_revision": ["v1"],
        }
    )
    assert reconciliation_index_from_frame(valid)[
        ("sarma", "global")
    ].canonical_label == ("sharma")
    with pytest.raises(ValueError, match="unique"):
        reconciliation_index_from_frame(pd.concat([valid, valid]))
    with pytest.raises(ValueError, match="cannot name"):
        reconciliation_index_from_frame(valid.assign(status="ambiguous"))


def test_anchor_evidence_rejects_invalid_values_and_conflicting_labels() -> None:
    with pytest.raises(ValueError, match="nonempty"):
        _evidence("", "ray")
    with pytest.raises(ValueError, match="support"):
        _evidence("rai", "ray", support=0)
    with pytest.raises(ValueError, match="similarity"):
        _evidence("rai", "ray", similarity=2)
    evidence = [
        _evidence("rai", "ray", canonical_id="anchor:ray"),
        _evidence("rai", "rey", canonical_id="anchor:ray"),
    ]
    with pytest.raises(ValueError, match="conflicting labels"):
        rank_anchor_candidates(evidence)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"min_support": 0}, "min_support"),
        ({"min_similarity": 2}, "min_similarity"),
    ],
)
def test_rank_rejects_invalid_thresholds(
    kwargs: dict[str, float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        rank_anchor_candidates([_evidence("rai", "ray")], **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"rank": 0}, "rank"),
        ({"total_support": 0}, "support totals"),
        ({"support_share": 0}, "support share"),
        ({"weighted_similarity": 2}, "similarity"),
        ({"sources": ()}, "provenance"),
        ({"min_support_threshold": 0}, "support threshold"),
        ({"min_similarity_threshold": 2}, "similarity threshold"),
        ({"eligible": False}, "eligibility"),
    ],
)
def test_ranked_candidate_rejects_inconsistent_fields(
    changes: dict[str, object], message: str
) -> None:
    candidate = rank_anchor_candidates([_evidence("rai", "ray")])[0]
    with pytest.raises(ValueError, match=message):
        replace(candidate, **changes)


def test_apply_reconciliation_rejects_invalid_inputs_and_contexts() -> None:
    with pytest.raises(ValueError, match="normalized column"):
        apply_reconciliation(pd.DataFrame({"name": ["A B"]}), {})
    records = pd.DataFrame({"surname_latin_normalized": ["rai"]})
    with pytest.raises(ValueError, match="context column"):
        apply_reconciliation(records, {}, context_column="missing")
    with pytest.raises(ValueError, match="fixed reconciliation context"):
        apply_reconciliation(records, {}, context="")
    with pytest.raises(ValueError, match="contexts must be nonempty"):
        apply_reconciliation(
            records.assign(reconciliation_context=""),
            {},
            context_column="reconciliation_context",
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"observed_form": None}, "nonnull"),
        ({"context": ""}, "nonempty strings"),
        ({"canonical_label": None}, "require a canonical"),
        ({"reason": ""}, "reasons"),
        ({"reconciliation_revision": ""}, "revisions"),
    ],
)
def test_decision_loader_rejects_invalid_fields(
    changes: dict[str, object], message: str
) -> None:
    frame = pd.DataFrame(
        {
            "observed_form": ["sarma"],
            "context": ["global"],
            "canonical_label": ["sharma"],
            "status": ["accepted"],
            "reason": ["single_supported_anchor"],
            "reconciliation_revision": ["v1"],
        }
    ).assign(**changes)
    with pytest.raises(ValueError, match=message):
        reconciliation_index_from_frame(frame)


def test_decision_loader_requires_its_schema() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        reconciliation_index_from_frame(pd.DataFrame({"observed_form": ["rai"]}))
