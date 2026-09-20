"""Behavioral regressions for the narrowly scoped initials exception."""

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from upnaam.adapters.electors import SOURCES, build_elector_artifact

LOOKUP = {
    "ಸುಬ್ಬರಾವ್": "subbarao",
    "ಸುಬ್ಬಾರಾವ್": "subbarao",
    "ರಾಮ": "rama",
    "ಗೌಡ": "gauda",
    "ರೈ": "rai",
    "ಲಕ್ಷ್ಮೀ": "lakshmi",
}


def run(tmp_path, people):
    base = {
        "id": "fixture",
        "relationship": "father",
        "age": 30,
        "sex": "male",
        "ac_name": "fixture",
        "district": "fixture",
        "part_no": 1,
        "year": 2017,
        "filename": "fixture.pdf",
        "deleted": False,
        "house_no": "1",
        "elector_name_en": None,
        "father_or_husband_name_en": None,
    }
    rows = [{**base, "number": i + 1, **p} for i, p in enumerate(people)]
    source, output = tmp_path / "electors.parquet", tmp_path / "surnames.parquet"
    pq.write_table(pa.Table.from_pylist(rows), source)
    build_elector_artifact(
        SOURCES["karnataka"],
        source,
        output,
        romanize_token=LOOKUP.get,
        romanization_revision="fixture",
    )
    return {r["source_number"]: r for r in pq.read_table(output).to_pylist()}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("T. Subbarow", "subbarow"),
        ("T.Subbarao", "subbarao"),
        ("T K Subbarao", "subbarao"),
        ("Subbarao T.", "subbarao"),
        ("ಟಿ. ಸುಬ್ಬರಾವ್", "subbarao"),
        ("ಟಿ ಸುಬ್ಬರಾವ್", "subbarao"),
        ("ಕೆ.ಎಂ.ಸುಬ್ಬಾರಾವ್", "subbarao"),
        ("ಟಿ. ರೈ", "rai"),
    ],
)
def test_initials_and_one_known_token_are_retained(tmp_path, name, expected):
    row = run(
        tmp_path, [{"elector_name": name, "father_or_husband_name": "Unrelated"}]
    )["1"]
    assert row["surname_latin_normalized"] == expected
    assert row["surname_evidence"] == "position"
    assert row["surname_provenance"] == "initials_single_token"
    assert row["surname_confidence"] is None


def test_relation_support_precedes_initials_fallback(tmp_path):
    row = run(
        tmp_path,
        [{"elector_name": "T. Subbarow", "father_or_husband_name": "Rama Subbarow"}],
    )["1"]
    assert row["surname_latin_normalized"] == "subbarow"
    assert row["surname_evidence"] == "relation"


def test_initials_name_can_supply_household_evidence(tmp_path):
    rows = run(
        tmp_path,
        [
            {"elector_name": "T. Subbarow", "father_or_husband_name": "Rama"},
            {"elector_name": "Ravi Subbarow", "father_or_husband_name": "Krishna"},
        ],
    )
    assert all(r["surname_latin_normalized"] == "subbarow" for r in rows.values())
    assert all(r["surname_evidence"] == "household" for r in rows.values())


@pytest.mark.parametrize(
    "name",
    [
        "Subbarow",
        "ಲಕ್ಷ್ಮೀ",
        "ಟಿ. ಅಪರಿಚಿತ",
        "T. K.",
        "T. Subbarow राम",
        "T. Subbarow русский",
        "T. Subbarow2",
        "T. ಸುಬ್ಬರಾವ್\ufffd",
        "T. ಸುಬ್ಬರಾವ್X",
        "ಬಿಬಿ ಸುಬ್ಬರಾವ್",
        "\u0c82. ಸುಬ್ಬರಾವ್",
    ],
)
def test_nearby_ambiguous_or_damaged_cases_still_abstain(tmp_path, name):
    rows = run(
        tmp_path,
        [
            {"elector_name": name, "father_or_husband_name": "Unrelated"},
            {"elector_name": name, "father_or_husband_name": "Unrelated"},
        ],
    )
    assert all(r["abstained"] for r in rows.values())


def test_household_relation_conflict_stays_unresolved(tmp_path):
    rows = run(
        tmp_path,
        [
            {"elector_name": "Ravi Gowda", "father_or_husband_name": "Ravi Sharma"},
            {"elector_name": "Mohan Gowda", "father_or_husband_name": "Krishna"},
        ],
    )
    assert rows["1"]["abstention_reason"] == "conflicting-evidence"


def test_existing_two_word_selection_unchanged(tmp_path):
    row = run(
        tmp_path,
        [{"elector_name": "Ravi Gowda", "father_or_husband_name": "Rama Gowda"}],
    )["1"]
    assert row["surname_latin_normalized"] == "gowda"
    assert row["surname_evidence"] == "relation"
