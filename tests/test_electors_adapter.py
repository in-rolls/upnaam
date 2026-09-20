"""State-parameterized elector artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from upnaam.adapters.electors import (
    SOURCES,
    build_elector_artifact,
    household_key,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_household_key_ignores_separators() -> None:
    assert household_key("p1", "1/22 A") == household_key("p1", "1:22a")
    assert household_key("p1", "") is None


def _roll(path: Path, rows: list[dict[str, object]]) -> Path:
    pq.write_table(pa.Table.from_pylist(rows), path)
    return path


@pytest.mark.parametrize("filename", ["electors.parquet", "elector's.parquet"])
def test_lakshadweep_uses_romanized_columns_and_house_evidence(
    tmp_path: Path, filename: str
) -> None:
    base = {
        "id": "PUV1",
        "relationship": "father",
        "age": "30",
        "sex": "Male",
        "ac_name": "1 Lakshadweep",
        "district": "Lakshadweep",
        "part_no": "1",
        "year": "2026",
        "filename": "part1",
        "deleted": False,
    }
    rows = [
        {
            **base,
            "number": "1",
            "elector_name": "ഫര്‍ഹാന്‍ കുന്നിനമേല്‍",
            "elector_name_en": "Farhan Kunninamel",
            "father_or_husband_name": "സൈലാനി",
            "father_or_husband_name_en": "Sailani",
            "house_no": "1/5 കുന്നിനമേല്‍",
            "house_no_en": "1/5 Kunninamel",
        },
        {
            **base,
            "number": "2",
            "elector_name": "ആമിന",
            "elector_name_en": "Amina",
            "father_or_husband_name": "അബ്ബാസ്‌",
            "father_or_husband_name_en": "Abbas",
            "house_no": "1:5 കുന്നിനമേല്‍",
            "house_no_en": "1:5 Kunninamel",
        },
    ]
    roll = _roll(tmp_path / filename, rows)
    out = tmp_path / f"resolved_{filename}"
    report = build_elector_artifact(SOURCES["lakshadweep"], roll, out)
    got = pq.read_table(out).to_pylist()
    assert report.rows == 2
    assert report.households == 1  # 1/5 and 1:5 are one house
    assert got[0]["surname_source_normalized"] == "kunninamel"
    assert got[0]["surname_evidence"] == "house"
    assert got[0]["name_source_raw"] == "ഫര്‍ഹാന്‍ കുന്നിനമേല്‍"
    assert got[0]["name_latin_raw"] == "Farhan Kunninamel"
    assert got[1]["abstained"]
    assert got[1]["abstention_reason"] == "no-evidence"
    assert got[0]["resolver_revision"] == "lakshadweep-elector-resolver-v2"


def test_malayalam_households_are_contiguous_despite_interleaved_serials(
    tmp_path: Path,
) -> None:
    base = {
        "id": "PUV1",
        "relationship": "father",
        "age": "30",
        "sex": "Male",
        "ac_name": "Lakshadweep",
        "district": "Lakshadweep",
        "part_no": "1",
        "year": "2026",
        "filename": "part1",
        "deleted": False,
        "elector_name": "പേര്",
        "father_or_husband_name": "പിതാവ്",
        "father_or_husband_name_en": "Abbas",
        "house_no_en": "1",
    }
    rows = [
        {
            **base,
            "number": "1",
            "house_no": "1അ",
            "elector_name_en": "Farhan Kunninamel",
        },
        {**base, "number": "2", "house_no": "1ബ", "elector_name_en": "Nadia Rahman"},
        {
            **base,
            "number": "3",
            "house_no": "1അ",
            "elector_name_en": "Amina Kunninamel",
        },
    ]
    roll = _roll(tmp_path / "electors.parquet", rows)
    out = tmp_path / "surnames.parquet"
    report = build_elector_artifact(SOURCES["lakshadweep"], roll, out)
    got = {r["source_number"]: r for r in pq.read_table(out).to_pylist()}
    assert report.households == 2
    for number in ("1", "3"):
        assert got[number]["household_size"] == 2
        assert got[number]["surname_latin_normalized"] == "kunninamel"
        assert got[number]["surname_evidence"] == "household"
    assert got["2"]["abstained"]


def test_household_key_preserves_malayalam_vowel_marks() -> None:
    assert household_key("p1", "1/5 കു") != household_key("p1", "1/5 കി")
    assert household_key("p1", "1/5 കു") == household_key("p1", "1:5 കു")


def test_karnataka_keeps_native_names_and_does_not_group_zero_houses(
    tmp_path: Path,
) -> None:
    base = {
        "id": "TEST1",
        "relationship": "father",
        "age": 30,
        "sex": "Male",
        "ac_name": "ಬೆಳಗಾವಿ",
        "district": "Test",
        "part_no": 1,
        "year": 2017,
        "filename": "AC0010001.pdf",
        "deleted": False,
        "elector_name": "ಶಿವ ಪಾಟೀಲ್",
        "father_or_husband_name": "ರಾಮ",
        "father_or_husband_name_en": "Rama",
    }
    rows = [
        {**base, "number": 1, "house_no": "12", "elector_name_en": "Shiva Patil"},
        {**base, "number": 2, "house_no": "12", "elector_name_en": "Geeta Patil"},
        {**base, "number": 3, "house_no": "0", "elector_name_en": "Shiva Patil"},
        {**base, "number": 4, "house_no": "0", "elector_name_en": "Geeta Patil"},
        {
            **base,
            "number": 5,
            "house_no": "12",
            "elector_name_en": "Basava Patil",
            "deleted": True,
        },
    ]
    roll = _roll(tmp_path / "electors.parquet", rows)
    out = tmp_path / "surnames.parquet"
    report = build_elector_artifact(
        SOURCES["karnataka"],
        roll,
        out,
        romanize_token={"ಶಿವ": "Shiva", "ಪಾಟೀಲ್": "Patil", "ರಾಮ": "Rama"}.get,
        romanization_revision="fixture",
    )
    got = {row["source_number"]: row for row in pq.read_table(out).to_pylist()}
    assert report.rows == 4
    assert report.households == 1
    assert got["1"]["surname_latin_normalized"] == "patil"
    assert got["1"]["name_source_raw"] == "ಶಿವ ಪಾಟೀಲ್"
    assert got["1"]["name_latin_raw"] == "Shiva Patil"
    for number in ("3", "4"):
        assert got[number]["abstained"]
        assert got[number]["household_id"] is None
        assert got[number]["household_size"] == 1
        assert got[number]["house_no_raw"] == "0"

    assert got["1"]["age_raw"] == "30"
    assert got["1"]["year"] == "2017"
    assert got["1"]["part_no"] == "1"
    assert got["1"]["ac_name_source_raw"] == "ಬೆಳಗಾವಿ"
    assert got["1"]["ac_name_latin_raw"] is None


def test_partial_name_retains_known_surname_and_excludes_expanded_initial(
    tmp_path: Path,
):
    base = {
        "id": "x",
        "relationship": "father",
        "age": 30,
        "sex": "female",
        "ac_name": "x",
        "district": "x",
        "part_no": 1,
        "year": 2017,
        "filename": "p.pdf",
        "deleted": False,
        "house_no": "1",
        "elector_name_en": None,
        "father_or_husband_name_en": None,
    }
    rows = [
        dict(
            base,
            number=1,
            elector_name="ಭಾರತಿ ಅಲ್ಸನ್ ಡಿಸೋಜಾ",
            father_or_husband_name="ಅಲ್ಸನ್ ಡಿಸೋಜಾ",
        ),
        dict(
            base,
            number=2,
            house_no="2",
            elector_name="ಕಾಂತರಾಜ ವೈ",
            father_or_husband_name="ವೈ ಬಿ ಯಲ್ಲಪ್ಪ",
        ),
        dict(
            base,
            number=3,
            house_no="3",
            elector_name="ಗೀತಾ ಗೌಡ",
            father_or_husband_name="ರಾಮ ಗೌಡ",
        ),
    ]
    roll = tmp_path / "roll.parquet"
    out = tmp_path / "surname.parquet"
    pq.write_table(pa.Table.from_pylist(rows), roll)
    lookup = {
        "ಭಾರತಿ": "bharati",
        "ಡಿಸೋಜಾ": "disoja",
        "ಕಾಂತರಾಜ": "kantharaja",
        "ವೈ": "vai",
        "ಬಿ": "bi",
        "ಯಲ್ಲಪ್ಪ": "yallappa",
        "ಗೀತಾ": "gita",
        "ಗೌಡ": "gauda",
        "ರಾಮ": "rama",
    }
    build_elector_artifact(
        SOURCES["karnataka"],
        roll,
        out,
        romanize_token=lookup.get,
        romanization_revision="test",
    )
    got = {r["source_number"]: r for r in pq.read_table(out).to_pylist()}
    assert got["1"]["surname_latin_normalized"] == "disoja"
    assert got["1"]["surname_raw"] == "ಡಿಸೋಜಾ"
    assert got["1"]["name_latin_raw"] is None
    assert got["2"]["surname_latin_normalized"] == "kantharaja"
    assert got["2"]["surname_provenance"] == "initials_single_token"
    assert got["3"]["surname_latin_normalized"] == "gauda"
    assert all(r["surname_confidence"] is None for r in got.values())


def test_karnataka_house_separators_cannot_merge_different_numbers():
    keys = [
        household_key("p", x, preserve_separators=True) for x in ["1/22", "12/2", "122"]
    ]
    assert len(set(keys)) == 3
    assert household_key("p", "1/22 A", preserve_separators=True) == household_key(
        "p", "1:22 A", preserve_separators=True
    )


def test_repeated_single_given_names_do_not_supply_surname_evidence(tmp_path: Path):
    base = {
        "id": "x",
        "relationship": "father",
        "age": 30,
        "sex": "female",
        "ac_name": "x",
        "district": "x",
        "part_no": 1,
        "year": 2017,
        "filename": "p.pdf",
        "deleted": False,
        "house_no": "1",
        "elector_name_en": "Lakshmi",
        "father_or_husband_name_en": "Rama",
        "elector_name": "ಲಕ್ಷ್ಮೀ",
        "father_or_husband_name": "ರಾಮ",
    }
    rows = [{**base, "number": i} for i in (1, 2)]
    roll = _roll(tmp_path / "roll.parquet", rows)
    out = tmp_path / "surnames.parquet"
    build_elector_artifact(
        SOURCES["karnataka"],
        roll,
        out,
        romanize_token={"ಲಕ್ಷ್ಮೀ": "lakshmi", "ರಾಮ": "rama"}.get,
        romanization_revision="fixture",
    )
    assert all(
        r["abstained"] and r["abstention_reason"] == "single-name-token"
        for r in pq.read_table(out).to_pylist()
    )


def test_kannada_short_surnames_and_damaged_tokens():
    from upnaam.adapters.kannada import KannadaEvidenceTokens

    tokens = KannadaEvidenceTokens({"ರೈ": "rai", "ವೈ": "vai", "ಗೌಡ": "gauda"}.get)
    assert [t.normalized for t in tokens("ರೈ ವೈ ಗೌಡ")] == ["rai", "gauda"]
    assert not tokens("ಗೌಡ\ufffd")
    assert not tokens(None)
    assert not tokens.has_multiple_words(None)
    assert tokens.has_multiple_words("ಅಪರಿಚಿತ ಗೌಡ")


def test_separated_zero_house_and_mixed_script_word_are_not_evidence():
    from upnaam.adapters.kannada import KannadaEvidenceTokens

    for house in ("0/0", "\u0ce6/\u0ce6", "00:00"):
        assert (
            household_key("p", house, zero_is_missing=True, preserve_separators=True)
            is None
        )
    tokens = KannadaEvidenceTokens({"ಗೌಡ": "gauda", "ರಾಮ": "rama"}.get)
    assert not tokens("ಗೌಡX")
    assert not tokens("Xಗೌಡ")
    assert not tokens("ಗೌಡ2")


def test_spelled_and_bare_kannada_initials_are_not_surnames():
    from upnaam.adapters.kannada import KannadaEvidenceTokens

    tokens = KannadaEvidenceTokens(
        {"ಎಸ": "esa", "ಯಂ": "yam", "ಚ": "cha", "ಗೌಡ": "gauda"}.get
    )
    assert [t.normalized for t in tokens("ಎಸ.ಯಂ.ಚ.ಗೌಡ")] == ["gauda"]
    assert not tokens.has_multiple_words("ಎಸ.ಯಂ.ಚ.ಗೌಡ")


def test_compound_initial_like_tokens_do_not_supply_surname_evidence():
    from upnaam.adapters.kannada import KannadaEvidenceTokens

    mappings = {
        "ಜೆಎಚ್": "jeech",
        "ಜಿಎಲ್": "jiel",
        "ಎಂಐಜಿ": "emaigi",
        "ಎಸಯಂ": "esayam",
        "ಅರ್ಜಿ": "arji",
        "ಬಿಬಿ": "bibi",
        "ಗೌಡ": "gauda",
        "ರೈ": "rai",
        "ರಾಮ": "rama",
    }
    tokens = KannadaEvidenceTokens(mappings.get)
    for raw in ("ಜೆಎಚ್", "ಜಿಎಲ್", "ಎಂಐಜಿ", "ಎಸಯಂ", "ಅರ್ಜಿ", "ಬಿಬಿ"):
        assert tokens(raw) == ()
        assert not tokens.has_multiple_words(raw + " ರಾಮ")
    assert [token.normalized for token in tokens("ರಾಮ ಗೌಡ")] == ["rama", "gauda"]
    assert [token.normalized for token in tokens("ರೈ ಗೌಡ")] == ["rai", "gauda"]
    assert tokens.has_multiple_words("ರಾಮ ಗೌಡ")
