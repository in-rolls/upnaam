"""Native Urdu corroboration preserves source identities and missing evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import TYPE_CHECKING

import pyarrow.parquet as pq
import pytest
from test_jk_english import write_source

from upnaam.adapters.arabic import arabic_tokens
from upnaam.adapters.electors import build_elector_artifact
from upnaam.adapters.jk_urdu import SOURCE, resolve_jk_urdu
from upnaam.cli import main

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def urdu_source(tmp_path: Path) -> tuple[Path, Path]:
    filename = "UACA032PS0001.pdf"
    variants = [
        {},
        {"elector_name": "نیلوفر ڈار", "relative_type": "خاوند"},
        {"elector_name": None, "name_candidate": "jjjj", "name_issue": "outline"},
        {"house_no": "0"},
        {"elector_name": "یوسف دار", "relative_name": None},
        {"house_no": None, "relative_type": "دیگر"},
        {"house_no": "30", "relative_issue": "outline"},
        {"elector_name": "سلیم ڈار میر", "relative_name": "جاوید میر"},
        {"elector_name": "جناب ب", "relative_name": "جناب ب", "house_no": "40"},
        {"elector_name": "سلیم Dar", "house_no": "50"},
        {"active": False},
        {"assembly_eligible": False},
        {"elector_name": "طاہر", "relative_name": "سلیم ڈار"},
    ]
    rows = []
    for index, variant in enumerate(variants, 1):
        row = {
            "filename": filename,
            "number": str(index),
            "id": None,
            "active": True,
            "assembly_eligible": True,
            "source_sha256": "0" * 64,
            "elector_name": "سلیم ڈار",
            "relative_name": "جاوید ڈار",
            "name_issue": None,
            "relative_issue": None,
            "relative_type": "باپ",
            "house_no": "10",
            "age": "30",
            "sex_candidate": None,
            "event_key": f"{filename}:3:{index}",
            "entry_event_key": f"{filename}:3:{index}",
            **variant,
        }
        row.setdefault("name_candidate", row["elector_name"])
        row["relative_candidate"] = row["relative_name"]
        rows.append(row)
    inventory, audit = write_source(tmp_path / "source", rows)
    payload = json.loads(audit.read_text())
    payload["parts"][0]["filename"] = filename
    payload["script_sha256"] = {"jk_urdu_unicode.py": "1" * 64}
    audit.write_text(json.dumps(payload))
    return inventory, audit


def test_urdu_cli_preserves_rows_and_exact_native_evidence(
    tmp_path: Path, urdu_source: tuple[Path, Path]
) -> None:
    output = tmp_path / "output's"
    main(["resolve-jk-urdu", *map(str, urdu_source), str(output)])
    rows = {
        row["source_number"]: row
        for row in pq.read_table(output / "surnames.parquet").to_pylist()
    }
    assert set(rows) == {str(i) for i in range(1, 14)} - {"11", "12"}
    assert rows["1"]["surname_source_normalized"] == "ڈار"
    assert rows["2"]["relationship_raw"] == "خاوند"
    assert rows["3"]["abstained"]
    assert rows["3"]["name_source_raw"] == "jjjj"
    assert rows["4"]["household_id"] is None
    assert rows["4"]["surname_source_normalized"] == "ڈار"
    assert all(rows[str(i)]["abstained"] for i in [5, 6, 7, 9, 10, 13])
    assert rows["8"]["abstention_reason"] == "conflicting-evidence"
    assert rows["13"]["relative_surname_candidate"] == "ڈار"
    for row in rows.values():
        for key in [
            "name_latin_raw",
            "relative_name_latin_raw",
            "surname_latin_raw",
            "surname_latin_normalized",
            "surname_canonical",
            "surname_confidence",
        ]:
            assert row[key] is None
    audit = json.loads((output / "audit.json").read_text())
    assert audit["counts"]["active_assembly"] == 11
    assert audit["counts"]["inactive_excluded"] == 1
    assert audit["counts"]["active_npr_excluded"] == 1
    assert "adapters/arabic.py" in audit["script_sha256"]


def test_urdu_marks_and_letter_variants_remain_distinct() -> None:
    value = "جناب ڈار دار بَٹ بٹ ب Dar ڈار۱"
    tokens = arabic_tokens(value)
    assert [token.raw for token in tokens] == ["ڈار", "دار", "بَٹ", "بٹ"]
    assert len({token.normalized for token in tokens}) == 4
    assert all(value[token.start : token.end] == token.raw for token in tokens)


@pytest.mark.parametrize("failure", ["count", "hash", "script", "filename"])
def test_urdu_source_failure_does_not_leave_partial_output(
    tmp_path: Path, urdu_source: tuple[Path, Path], failure: str
) -> None:
    inventory, audit = urdu_source
    payload = json.loads(audit.read_text())
    if failure == "count":
        payload["parts"][0]["active_assembly"] += 1
    elif failure == "hash":
        payload["artifacts"]["inventory.parquet"] = "2" * 64
    elif failure == "script":
        payload["script_sha256"] = {"jk_urdu_rows.py": "1" * 64}
    else:
        payload["parts"][0]["filename"] = "UACA035PS0001.pdf"
    audit.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match=r"audit|parser|hash"):
        resolve_jk_urdu(inventory, audit, tmp_path / "failed")
    assert not (tmp_path / "failed").exists()
    assert not list(tmp_path.glob(".jk-urdu-*"))


@pytest.mark.parametrize(
    "option",
    [
        {"position": "last"},
        {"confidence_diagnostic": True},
        {"token_romanization": True},
        {"exact_spelling": False},
    ],
)
def test_urdu_rejects_incompatible_inference_policy(
    tmp_path: Path, option: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="Arabic evidence requires"):
        build_elector_artifact(
            replace(SOURCE, **option), tmp_path / "missing", tmp_path / "output"
        )


@pytest.mark.parametrize("form", ["ڈار", "دار"])
def test_urdu_map_preserves_native_evidence_and_abstentions(
    tmp_path: Path, urdu_source: tuple[Path, Path], form: str
) -> None:
    native, mapped = tmp_path / "native", tmp_path / "mapped"
    baseline = resolve_jk_urdu(*urdu_source, native)
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({form: "Dar"}))
    main(
        [
            "resolve-jk-urdu",
            *map(str, urdu_source),
            str(mapped),
            "--romanization-map",
            str(mapping),
        ]
    )
    before = pq.read_table(native / "surnames.parquet").to_pylist()
    after = pq.read_table(mapped / "surnames.parquet").to_pylist()
    allowed = {
        "surname_latin_raw",
        "surname_latin_normalized",
        "surname_canonical",
        "canonicalization_status",
        "canonicalization_reason",
        "resolver_revision",
    }
    for old, new in zip(before, after, strict=True):
        assert {k: v for k, v in old.items() if k not in allowed} == {
            k: v for k, v in new.items() if k not in allowed
        }
        expected = (
            "dar"
            if not old["abstained"] and old["surname_source_normalized"] == form
            else None
        )
        assert new["surname_latin_normalized"] == expected
        assert new["surname_canonical"] == expected
    report = json.loads((mapped / "audit.json").read_text())
    assert report["resolver"]["evidence"] == baseline["resolver"]["evidence"]
    assert (
        report["romanization"]["mapping_sha256"]
        == hashlib.sha256(mapping.read_bytes()).hexdigest()
    )
    assert (
        report["resolver"]["romanization_revision"]
        == report["romanization"]["mapping_sha256"]
    )
    assert report["romanization"]["mapped_selections"] == (3 if form == "ڈار" else 0)
    assert report["romanization"]["unmapped_selections"] == (0 if form == "ڈار" else 3)
    assert (native / "electors.parquet").read_bytes() == (
        mapped / "electors.parquet"
    ).read_bytes()


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        "[]",
        '{"ڈار":"Dar","ڈار":"Daar"}',
        '{"ڈار":""}',
        '{"ڈار":null}',
        '{"ڈار":"Da r"}',
        '{"ڈار":"D"}',
        '{"ڈار":"Dar1"}',
        '{"ڈار":"D\u0430r"}',
        '{"جناب":"Janab"}',
        '{"ب":"Baa"}',
        '{"سلیم ڈار":"Dar"}',
        '{"Dar":"Dar"}',
        '{"ڈار۱":"Dar"}',
        '{"शर्मा":"Sharma"}',
    ],
)
def test_urdu_invalid_map_fails_before_output_creation(
    tmp_path: Path, urdu_source: tuple[Path, Path], payload: str
) -> None:
    mapping = tmp_path / "map.json"
    mapping.write_text(payload)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="Romanization map"):
        resolve_jk_urdu(*urdu_source, output, romanization_map=mapping)
    assert not output.exists()


@pytest.mark.parametrize("mapped", [False, True])
def test_nastaleeq_profile_retains_non_arial_source_keys(
    tmp_path: Path, urdu_source: tuple[Path, Path], mapped: bool
) -> None:
    import pyarrow as pa

    inventory, audit = urdu_source
    table = pq.read_table(inventory)
    rows = table.to_pylist()
    for row in rows:
        for field in ("filename", "event_key", "entry_event_key"):
            row[field] = row[field].replace("UACA032", "UACA028")
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), inventory)
    payload = json.loads(audit.read_text())
    payload["parts"][0]["filename"] = "UACA028PS0001.pdf"
    payload["artifacts"]["inventory.parquet"] = hashlib.sha256(
        inventory.read_bytes()
    ).hexdigest()
    payload["script_sha256"]["jk_urdu_nastaleeq.py"] = "3" * 64
    audit.write_text(json.dumps(payload))
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"ڈار": "Dar"}))
    output = tmp_path / "nastaleeq"
    result = resolve_jk_urdu(
        inventory, audit, output, romanization_map=mapping if mapped else None
    )
    found = pq.read_table(output / "surnames.parquet").to_pylist()
    assert result["counts"]["active_assembly"] == 11
    assert all(
        row["elector_id"].startswith("jk-urdu-2018-nastaleeq:UACA028") for row in found
    )
    assert sum(row["surname_latin_normalized"] is not None for row in found) == (
        3 if mapped else 0
    )


def test_nastaleeq_own_names_without_corroboration_still_abstain(
    tmp_path: Path, urdu_source: tuple[Path, Path]
) -> None:
    import pyarrow as pa

    inventory, audit = urdu_source
    table = pq.read_table(inventory)
    rows = table.to_pylist()
    for row in rows:
        row["relative_name"] = None
        row["relative_candidate"] = None
        row["relative_type"] = None
        row["house_no"] = None
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), inventory)
    payload = json.loads(audit.read_text())
    payload["artifacts"]["inventory.parquet"] = hashlib.sha256(
        inventory.read_bytes()
    ).hexdigest()
    payload["script_sha256"]["jk_urdu_nastaleeq.py"] = "3" * 64
    audit.write_text(json.dumps(payload))
    output = tmp_path / "own-only"
    resolve_jk_urdu(inventory, audit, output)
    found = pq.read_table(output / "surnames.parquet").to_pylist()
    assert len(found) == 11
    assert all(row["abstained"] for row in found)


@pytest.mark.parametrize("mapped", [False, True])
def test_calibrated_profile_records_distinct_source_and_resolver_revisions(
    tmp_path: Path, urdu_source: tuple[Path, Path], mapped: bool
) -> None:
    inventory, audit = urdu_source
    payload = json.loads(audit.read_text())
    payload["script_sha256"]["promote_jk_urdu.py"] = "4" * 64
    audit.write_text(json.dumps(payload))
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"ڈار": "Dar"}))
    output = tmp_path / "calibrated"
    result = resolve_jk_urdu(
        inventory, audit, output, romanization_map=mapping if mapped else None
    )
    rows = pq.read_table(output / "surnames.parquet").to_pylist()
    assert result["source_revision"] == "jk-urdu-2018-calibrated"
    assert result["revision"] == (
        "jk-urdu-elector-resolver-v4" if mapped else "jk-urdu-elector-resolver-v3"
    )
    assert all(row["elector_id"].startswith("jk-urdu-2018-calibrated:") for row in rows)
