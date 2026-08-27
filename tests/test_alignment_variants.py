from upnaam.alignment import align_names
from upnaam.clustering import VariantEvidence, cluster_variants
from upnaam.edit_model import character_edits, summarize_edits


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
