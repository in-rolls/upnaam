"""Native-script handoff invariants on synthetic electoral records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import TYPE_CHECKING

import pyarrow.parquet as pq
import pytest
from test_jk_english import write_source

from upnaam.adapters.devanagari import devanagari_tokens
from upnaam.adapters.electors import build_elector_artifact
from upnaam.adapters.jk_hindi import SOURCE, resolve_jk_hindi
from upnaam.cli import main
from upnaam.normalization import normalize_name

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def hindi_source(tmp_path: Path) -> tuple[Path, Path]:
    variants = [
        {"elector_name": "अनिल शर्मा", "relative_name": "सुनील शर्मा"},
        {
            "elector_name": "नीता शर्मा",
            "relative_name": "अनिल शर्मा",
            "relative_type": "पति",
        },
        {"elector_name": None, "name_candidate": "नी�ता", "name_issue": "rendering"},
        {"elector_name": "अनिल राम", "relative_name": "सुनील राम", "house_no": "\u0966"},
        {"elector_name": "लीला शार्मा", "relative_name": None},
        {
            "elector_name": "अनिल कपूर",
            "relative_name": "अनिल कपूर",
            "relative_type": "अन्य",
            "house_no": None,
        },
        {
            "elector_name": "अनिल कुमार",
            "relative_name": "सुनील कुमार",
            "relative_issue": "rendering",
            "house_no": "30",
        },
        {"elector_name": "अनिल शर्मा कुमार", "relative_name": "सुनील कुमार"},
        {"elector_name": "श्री अ", "relative_name": "श्री ब", "house_no": "40"},
        {"elector_name": "अनिल Sharma", "house_no": "50"},
        {"active": False},
        {"assembly_eligible": False},
        {"elector_name": "गीता", "relative_name": "अनिल शर्मा"},
    ]
    rows = []
    for index, variant in enumerate(variants, 1):
        row = {
            "filename": "HACA057PS0001.pdf",
            "number": str(index),
            "id": None,
            "active": True,
            "assembly_eligible": True,
            "source_sha256": "0" * 64,
            "elector_name": "अनिल शर्मा",
            "relative_name": None,
            "name_issue": None,
            "relative_issue": None,
            "relative_type": "पिता",
            "house_no": "10",
            "age": "30",
            "sex_candidate": None,
            "event_key": f"HACA057PS0001.pdf:3:{index}",
            "entry_event_key": f"HACA057PS0001.pdf:3:{index}",
            **variant,
        }
        row.setdefault("name_candidate", row["elector_name"])
        row["relative_candidate"] = row["relative_name"]
        rows.append(row)
    inventory, audit = write_source(tmp_path / "source", rows)
    payload = json.loads(audit.read_text())
    payload["parts"][0]["filename"] = "HACA057PS0001.pdf"
    payload["script_sha256"] = {"jk_hindi_rows.py": "1" * 64}
    audit.write_text(json.dumps(payload))
    return inventory, audit


def test_native_cli_preserves_source_and_never_invents_latin(
    tmp_path: Path, hindi_source: tuple[Path, Path]
) -> None:
    output = tmp_path / "output's"
    main(["resolve-jk-hindi", *map(str, hindi_source), str(output)])
    rows = {
        r["source_number"]: r
        for r in pq.read_table(output / "surnames.parquet").to_pylist()
    }
    assert set(rows) == {str(i) for i in range(1, 14)} - {"11", "12"}
    assert rows["1"]["surname_source_normalized"] == "शर्मा"
    assert rows["2"]["relationship_raw"] == "पति"
    assert rows["3"]["abstained"]
    assert rows["3"]["name_source_raw"] == "नी�ता"
    assert rows["4"]["surname_source_normalized"] == "राम"
    assert rows["4"]["household_id"] is None
    assert rows["5"]["abstained"]
    assert rows["6"]["abstained"]
    assert rows["7"]["abstained"]
    assert rows["8"]["abstention_reason"] == "conflicting-evidence"
    assert rows["9"]["abstention_reason"] == "no-eligible-token"
    assert rows["10"]["abstained"]
    for row in rows.values():
        for field in (
            "name_latin_raw",
            "relative_name_latin_raw",
            "surname_latin_raw",
            "surname_latin_normalized",
            "surname_canonical",
            "surname_confidence",
        ):
            assert row[field] is None
        if not row["abstained"]:
            assert (
                normalize_name(row["surname_raw"]) == row["surname_source_normalized"]
            )
            assert row["surname_raw"] in row["name_source_raw"]
            assert row["canonicalization_reason"] == "latin_form_unavailable"
    assert rows["13"]["abstained"]
    assert rows["13"]["relative_surname_candidate"] == "शर्मा"
    report = json.loads((output / "audit.json").read_text())
    assert report["counts"]["active_assembly"] == 11
    assert report["counts"]["names_withheld"] == 2
    assert report["counts"]["active_npr_excluded"] == 1
    assert report["counts"]["inactive_excluded"] == 1


@pytest.mark.parametrize("failure", ["count", "hash", "script", "filename"])
def test_hindi_validation_is_atomic(
    tmp_path: Path, hindi_source: tuple[Path, Path], failure: str
) -> None:
    inventory, audit = hindi_source
    payload = json.loads(audit.read_text())
    if failure == "count":
        payload["parts"][0]["active_assembly"] += 1
    elif failure == "hash":
        payload["artifacts"]["inventory.parquet"] = "2" * 64
    elif failure == "script":
        payload["script_sha256"] = {"jk_english_rows.py": "1" * 64}
    else:
        payload["parts"][0]["filename"] = "EACA047PS0001.pdf"
    audit.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match=r"audit|parser|hash"):
        resolve_jk_hindi(inventory, audit, tmp_path / "failed")
    assert not (tmp_path / "failed").exists()
    assert not list(tmp_path.glob(".jk-hindi-*"))


def test_devanagari_marks_and_source_spans() -> None:
    value = "श्री राम सिंह शार्मा शर्मा क़ादिर क़ादिर अ. Aशर्मा 123"
    tokens = devanagari_tokens(value)
    assert [t.raw for t in tokens] == ["राम", "सिंह", "शार्मा", "शर्मा", "क़ादिर", "क़ादिर"]
    assert all(value[t.start : t.end] == t.raw for t in tokens)
    assert tokens[-1].normalized == tokens[-2].normalized
    assert tokens[2].normalized != tokens[3].normalized


@pytest.mark.parametrize(
    "option",
    [
        {"position": "last"},
        {"confidence_diagnostic": True},
        {"token_romanization": True},
        {"exact_spelling": False},
    ],
)
def test_incompatible_native_mode_is_rejected(
    tmp_path: Path, option: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="Devanagari evidence requires"):
        build_elector_artifact(
            replace(SOURCE, **option), tmp_path / "missing", tmp_path / "output"
        )


def test_romanization_is_attached_after_selection_without_changing_evidence(
    tmp_path: Path, hindi_source: tuple[Path, Path]
) -> None:
    original, translated = tmp_path / "native", tmp_path / "translated"
    baseline = resolve_jk_hindi(*hindi_source, original)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps({"शर्मा": "Sharma", "शार्मा": "Sharma", "कुमार": "Kumar"})
    )
    main(
        [
            "resolve-jk-hindi",
            *map(str, hindi_source),
            str(translated),
            "--romanization-map",
            str(mapping),
        ]
    )
    before = pq.read_table(original / "surnames.parquet").to_pylist()
    after = pq.read_table(translated / "surnames.parquet").to_pylist()
    changed = {
        "surname_latin_raw",
        "surname_latin_normalized",
        "surname_canonical",
        "canonicalization_status",
        "canonicalization_reason",
        "resolver_revision",
    }
    for native, latin in zip(before, after, strict=True):
        assert {k: v for k, v in native.items() if k not in changed} == {
            k: v for k, v in latin.items() if k not in changed
        }
        assert latin["surname_confidence"] is None
        assert latin["name_latin_raw"] is None
        assert latin["relative_name_latin_raw"] is None
        if native["abstained"]:
            assert latin["surname_latin_normalized"] is None
        elif native["surname_source_normalized"] == "शर्मा":
            assert latin["surname_latin_raw"] == "Sharma"
            assert latin["surname_latin_normalized"] == "sharma"
            assert latin["surname_canonical"] == "sharma"
        elif native["surname_source_normalized"] == "राम":
            assert latin["surname_latin_normalized"] is None
            assert latin["canonicalization_reason"] == "latin_form_unavailable"
    report = json.loads((translated / "audit.json").read_text())
    assert report["resolver"]["evidence"] == baseline["resolver"]["evidence"]
    assert report["romanization"]["mapped_selections"] == sum(
        row["surname_latin_normalized"] is not None for row in after
    )
    assert report["romanization"]["unmapped_selections"] > 0
    assert (
        report["romanization"]["mapping_sha256"]
        == hashlib.sha256(mapping.read_bytes()).hexdigest()
    )
    assert (
        report["resolver"]["romanization_revision"]
        == report["romanization"]["mapping_sha256"]
    )


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        "[]",
        '{"शर्मा":"Sharma","शर्मा":"Sarma"}',
        '{"क़ादिर":"Qadir","क़ादिर":"Kadir"}',
        '{"शर्मा":""}',
        '{"शर्मा":null}',
        '{"शर्मा":"Sha rma"}',
        '{"शर्मा":"S"}',
        '{"शर्मा":"Sharm\u0430"}',
        '{"शर्मा":"Sharm�"}',
        '{"शर्मा":"Sharma1"}',
        '{"श्री":"Shri"}',
        '{"अ":"Aaa"}',
        '{"शर्मा कुमार":"Sharma"}',
        '{"Sharma":"Sharma"}',
    ],
)
def test_bad_romanization_maps_fail_before_output_creation(
    tmp_path: Path, hindi_source: tuple[Path, Path], payload: str
) -> None:
    mapping, output = tmp_path / "mapping.json", tmp_path / "output"
    mapping.write_text(payload)
    with pytest.raises(ValueError, match="Romanization map"):
        resolve_jk_hindi(*hindi_source, output, romanization_map=mapping)
    assert not output.exists()


@pytest.mark.parametrize("missing", ["lookup", "revision"])
def test_native_romanization_requires_both_lookup_and_revision(
    tmp_path: Path, missing: str
) -> None:
    with pytest.raises(ValueError, match="lookup and its revision"):
        build_elector_artifact(
            SOURCE,
            tmp_path / "missing",
            tmp_path / "output",
            romanize_token=None if missing == "lookup" else lambda _: "sharma",
            romanization_revision=None if missing == "revision" else "a" * 64,
        )


def test_invalid_romanization_callback_cannot_leave_an_artifact(
    tmp_path: Path, hindi_source: tuple[Path, Path]
) -> None:
    prepared, output = tmp_path / "native", tmp_path / "bad.parquet"
    resolve_jk_hindi(*hindi_source, prepared)
    with pytest.raises(ValueError, match="one ASCII letter token"):
        build_elector_artifact(
            SOURCE,
            prepared / "electors.parquet",
            output,
            romanize_token=lambda _: "sha rma",
            romanization_revision="a" * 64,
        )
    assert not output.exists()
    assert not output.with_suffix(".parquet.tmp").exists()


def test_distinct_ids_with_one_serial_keep_two_records_and_no_false_household(
    tmp_path: Path, hindi_source: tuple[Path, Path]
) -> None:
    inventory, _ = hindi_source
    records = pq.read_table(inventory).to_pylist()[:2]
    records[0].update(
        id="AAA1111111", relative_name=None, relative_candidate=None, house_no=None
    )
    records[1].update(
        number=records[0]["number"],
        id="BBB2222222",
        relative_name=None,
        relative_candidate=None,
        house_no=None,
    )
    rebuilt, new_audit = write_source(tmp_path / "collision", records)
    payload = json.loads(new_audit.read_text())
    payload["parts"][0]["filename"] = records[0]["filename"]
    payload["script_sha256"] = {"jk_hindi_rows.py": "1" * 64}
    new_audit.write_text(json.dumps(payload))
    output = tmp_path / "resolved-collision"
    resolve_jk_hindi(rebuilt, new_audit, output)
    rows = pq.read_table(output / "surnames.parquet").to_pylist()
    assert len(rows) == 2
    assert len({r["elector_id"] for r in rows}) == 2
    assert {r["source_elector_id"] for r in rows} == {"AAA1111111", "BBB2222222"}
    assert all(
        r["source_number"] == "1"
        and r["household_id"] is None
        and r["household_size"] == 1
        and r["abstained"]
        for r in rows
    )


@pytest.mark.parametrize("collision", ["same_id", "missing_id", "same_entry_key"])
def test_ambiguous_inventory_identity_is_rejected(
    tmp_path: Path, hindi_source: tuple[Path, Path], collision: str
) -> None:
    inventory, _ = hindi_source
    records = pq.read_table(inventory).to_pylist()[:2]
    records[0]["id"] = "AAA1111111"
    records[1].update(number=records[0]["number"], id="BBB2222222")
    if collision == "same_id":
        records[1]["id"] = records[0]["id"]
    elif collision == "missing_id":
        records[0]["id"] = None
    else:
        records[1]["entry_event_key"] = records[0]["entry_event_key"]
    rebuilt, audit = write_source(tmp_path / "collision", records)
    payload = json.loads(audit.read_text())
    payload["parts"][0]["filename"] = records[0]["filename"]
    payload["script_sha256"] = {"jk_hindi_rows.py": "1" * 64}
    audit.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="repeats"):
        resolve_jk_hindi(rebuilt, audit, tmp_path / "invalid")
