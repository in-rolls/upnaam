"""Relative candidates cannot contaminate the recorded surname evidence pass."""

from dataclasses import replace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from upnaam.adapters.electors import SOURCES, build_elector_artifact
from upnaam.corroboration import CorroboratedSurname, resolve_household
from upnaam.relative import suggest_relative_surnames


def suggest(members, relationships=None, position=None):
    recorded = resolve_household(members, reject_evidence_conflicts=True)
    candidates = suggest_relative_surnames(
        members,
        recorded,
        relationships=relationships or ["father"] * len(members),
        relative_position=position,
    )
    return recorded, candidates


def test_shastri_is_a_separate_candidate_under_explicit_policy():
    recorded, candidates = suggest([("Asha", "Ravi Shastri")], ["husband"], "last")
    assert recorded[0].abstained
    assert candidates[0].surname == "shastri"
    assert candidates[0].surname_raw == "Shastri"
    assert candidates[0].relationship == "husband"
    assert candidates[0].evidence == "relative-position-policy"
    assert candidates[0].abstention_reason is None


def test_no_default_position_assumption():
    _, candidates = suggest([("Asha", "Ravi Shastri")])
    assert candidates[0].abstention_reason == "no-relative-surname-evidence"


@pytest.mark.parametrize(
    "relationship", ["father", "mother", "husband", "wife", "spouse"]
)
def test_explicit_relationships_and_first_position(relationship):
    _, candidates = suggest([("Asha", "Shastri Ravi")], [relationship], "first")
    assert candidates[0].surname == "shastri"


@pytest.mark.parametrize("relationship", [None, "", "guardian", "father_or_husband"])
def test_unknown_or_ambiguous_relationship_cannot_inherit(relationship):
    _, candidates = suggest([("Asha", "Ravi Shastri")], [relationship], "last")
    assert candidates[0].abstention_reason == "unsupported-relationship"


@pytest.mark.parametrize(
    ("name", "relative"),
    [
        ("", "Ravi Shastri"),
        ("Asha", "Ravi"),
        ("Asha", "R. Shastri"),
        ("Asha Devi", "Ravi Shastri"),
    ],
)
def test_empty_names_short_relatives_and_ambiguous_own_names_abstain(name, relative):
    _, candidates = suggest([(name, relative)], position="last")
    assert candidates[0].surname is None
    assert candidates[0].abstention_reason


def test_recorded_and_conflicting_evidence_take_precedence():
    _, candidates = suggest([("Asha Shastri", "Ravi Shastri")], position="last")
    assert candidates[0].abstention_reason == "recorded-surname-available"
    conflict = CorroboratedSurname(None, None, None, None, "conflicting-evidence")
    candidates = suggest_relative_surnames(
        [("Asha", "Ravi Shastri")],
        [conflict],
        relationships=["husband"],
        relative_position="last",
    )
    assert candidates[0].abstention_reason == "conflicting-evidence"


def test_exact_relative_link_uses_recorded_evidence_without_position_rule():
    recorded, candidates = suggest(
        [
            ("Asha", "Ravi Shastri"),
            ("Ravi Shastri", "Mohan Shastri"),
        ]
    )
    assert recorded[0].abstained
    assert candidates[0].surname == "shastri"
    assert candidates[0].evidence == "matched-relative-recorded-surname"


def test_duplicate_relative_links_abstain_even_with_position_policy():
    _, candidates = suggest(
        [
            ("Asha", "Ravi Shastri"),
            ("Ravi Shastri", "Mohan Shastri"),
            ("Ravi Shastri", "Krishna Shastri"),
        ],
        position="last",
    )
    assert candidates[0].abstention_reason == "ambiguous-relative-match"


def test_unresolved_relative_cannot_be_rescued_by_position_or_recursion():
    _, candidates = suggest(
        [("Asha", "Ravi Shastri"), ("Ravi Shastri", "Mohan")], position="last"
    )
    assert candidates[0].abstention_reason == "relative-surname-unresolved"
    _, candidates = suggest(
        [("Asha", "Ravi Shastri"), ("Kavita", "Asha")], position="last"
    )
    assert candidates[0].surname == "shastri"
    assert candidates[1].surname is None


def test_invalid_inputs():
    with pytest.raises(ValueError, match="equal lengths"):
        suggest_relative_surnames([], [], relationships=["father"])
    with pytest.raises(ValueError, match="relative_position"):
        suggest_relative_surnames([], [], relationships=[], relative_position="middle")


def test_artifact_preserves_abstention_and_candidate_separately(tmp_path):
    base = {
        "id": "fixture",
        "relationship": "husband",
        "age": 30,
        "sex": "female",
        "ac_name": "fixture",
        "district": "fixture",
        "part_no": 1,
        "year": 2017,
        "filename": "fixture.pdf",
        "deleted": False,
        "house_no": "0",
        "elector_name": "Asha",
        "father_or_husband_name": "Ravi Shastri",
        "number": 1,
    }
    source, output = tmp_path / "source.parquet", tmp_path / "surnames.parquet"
    pq.write_table(pa.Table.from_pylist([base]), source)
    spec = replace(
        SOURCES["telangana"], relative_position="last", zero_house_is_missing=True
    )
    report = build_elector_artifact(spec, source, output)
    row = pq.read_table(output).to_pylist()[0]
    assert row["surname_latin_normalized"] is None
    assert row["abstained"]
    assert row["relative_surname_candidate"] == "shastri"
    assert row["relative_surname_relationship"] == "husband"
    assert row["surname_confidence"] is None
    assert report.evidence == {"abstained": 1}


def test_empty_elector_never_inherits_in_recorded_pass():
    (result,) = resolve_household([("", "Ravi Shastri")], position="last")
    assert result.abstained
