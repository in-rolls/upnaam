import pandas as pd
import pytest

from upnaam.canonicalization import (
    apply_canonical_map,
    canonical_map_from_frame,
    generate_variant_candidates,
)


def test_similarity_generates_candidates_without_declaring_a_mapping() -> None:
    candidates = generate_variant_candidates(
        {"jadhab": 12, "jadhav": 100, "sharma": 50}
    )
    assert [(item.left, item.right) for item in candidates] == [("jadhab", "jadhav")]


def test_candidate_blocking_does_not_drop_short_tokens() -> None:
    candidates = generate_variant_candidates(
        {"ra": 2, "rai": 3}, max_distance=1, min_similarity=0.6
    )
    assert [(item.left, item.right) for item in candidates] == [("ra", "rai")]


def test_apply_map_preserves_normalized_spelling_and_records_status() -> None:
    records = pd.DataFrame(
        {
            "surname_latin_normalized": ["jadhab", "jadhav", "sharma", None, None],
            "abstained": [False, False, False, False, True],
        }
    )
    result = apply_canonical_map(
        records, {"jadhab": "jadhav", "jadhav": "jadhav"}, revision="map-2026-01"
    )
    assert result["surname_latin_normalized"].tolist()[:3] == [
        "jadhab",
        "jadhav",
        "sharma",
    ]
    assert result["surname_canonical"].tolist()[:3] == [
        "jadhav",
        "jadhav",
        "sharma",
    ]
    assert result["canonicalization_status"].tolist() == [
        "variant_mapped",
        "canonical_identity",
        "identity_unmapped",
        "normalization_unavailable",
        "not_applicable",
    ]
    assert pd.isna(result.loc[2, "canonicalization_provenance"])
    assert set(result["canonicalization_revision"]) == {"map-2026-01"}


def test_map_loader_rejects_ambiguous_variants() -> None:
    frame = pd.DataFrame(
        {"variant": ["sarma", "sarma"], "canonical": ["sharma", "sarma"]}
    )
    with pytest.raises(ValueError, match="unique"):
        canonical_map_from_frame(frame)


def test_map_loader_rejects_non_idempotent_chains() -> None:
    frame = pd.DataFrame(
        {"variant": ["sarma", "sharma"], "canonical": ["sharma", "sharmaa"]}
    )
    with pytest.raises(ValueError, match="idempotent"):
        canonical_map_from_frame(frame)


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (pd.DataFrame({"variant": ["rai"]}), "missing"),
        (pd.DataFrame({"variant": [None], "canonical": ["rai"]}), "nonnull"),
        (pd.DataFrame({"variant": [1], "canonical": ["rai"]}), "strings"),
    ],
)
def test_map_loader_rejects_malformed_tables(frame: pd.DataFrame, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        canonical_map_from_frame(frame)
