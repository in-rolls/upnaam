import pytest

from upnaam.canonicalization import (
    EvidenceTier,
    VariantEvidence,
    align_names,
    character_edits,
    cluster_variants,
    summarize_edits,
)


def test_alignment_describes_exact_substitution_and_gap() -> None:
    operations = align_names("Poorna Devi", "Purna Devi Sharma")
    assert [operation.kind for operation in operations] == [
        "substitute",
        "exact",
        "external_only",
    ]
    assert (
        operations[0].roll_token,
        operations[0].external_token,
        operations[-1].external_token,
    ) == ("poorna", "purna", "sharma")


def test_alignment_handles_empty_side() -> None:
    operations = align_names(None, "Ram")
    assert len(operations) == 1
    assert operations[0].kind == "external_only"


def test_character_edit_summary_counts_observations() -> None:
    edits = character_edits("poorna", "purna")
    assert any(edit.operation == "delete" for edit in edits)
    summary = summarize_edits([("poorna", "purna"), ("poorna", "purna")])
    assert summary["substitution_pairs"] == 2
    assert summary["unique_substitution_pairs"] == 1
    assert summary["pairs"][0]["count"] == 2


def test_clustering_requires_direct_complete_link_evidence() -> None:
    evidence = [
        VariantEvidence("aana", "ana", 3, 0.9, "ration"),
        VariantEvidence("ana", "anna", 3, 0.9, "ration"),
    ]
    mappings = cluster_variants(evidence)
    clusters = {}
    for mapping in mappings:
        clusters.setdefault(mapping.canonical, set()).add(mapping.variant)
    assert sorted(map(len, clusters.values())) == [1, 2]


def test_clustering_validates_thresholds_and_filters_weak_edges() -> None:
    weak = [VariantEvidence("ram", "rama", 1, 0.9, "ration")]
    assert cluster_variants(weak) == ()
    for support, similarity in [(0, 0.8), (1, -0.1), (1, 1.1)]:
        try:
            cluster_variants(weak, min_support=support, min_similarity=similarity)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid threshold was accepted")


def test_clustering_rejects_string_only_edges_by_default() -> None:
    evidence = [
        VariantEvidence(
            "jadhab",
            "jadhav",
            10,
            0.83,
            "edit_candidates",
            evidence_tier=EvidenceTier.STRING_ONLY,
        )
    ]
    assert cluster_variants(evidence) == ()


def test_preferred_spelling_precedes_frequency_and_lexical_ties() -> None:
    evidence = [
        VariantEvidence("sarma", "sharma", 3, 0.9, "ration", preferred="sharma")
    ]
    mappings = cluster_variants(evidence, frequencies={"sarma": 100, "sharma": 1})
    assert {mapping.canonical for mapping in mappings} == {"sharma"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"left": "", "right": "rai", "support": 1, "similarity": 1},
        {"left": "ray", "right": "rai", "support": 0, "similarity": 1},
        {"left": "ray", "right": "rai", "support": 1, "similarity": 2},
        {
            "left": "ray",
            "right": "rai",
            "support": 1,
            "similarity": 1,
            "preferred": "roy",
        },
    ],
)
def test_variant_evidence_rejects_malformed_claims(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"must|between|nonempty"):
        VariantEvidence(source="test", **kwargs)  # type: ignore[arg-type]
