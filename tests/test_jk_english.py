"""J&K inventory boundaries, provenance and source-aware corroboration."""

from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from upnaam.adapters.jk_english import resolve_jk_english
from upnaam.artifacts import sha256_file
from upnaam.cli import main

if TYPE_CHECKING:
    from pathlib import Path


def write_source(root: Path, rows: list[dict[str, object]]) -> tuple[Path, Path]:
    root.mkdir(exist_ok=True)
    inventory = root / "inventory's.parquet"
    pq.write_table(pa.Table.from_pylist(rows), inventory)
    counts = Counter(
        {
            "inventory": len(rows),
            "active_total": 0,
            "active_npr": 0,
            "active_assembly": 0,
        }
    )
    for row in rows:
        if row["active"]:
            counts["active_total"] += 1
            counts["active_assembly" if row["assembly_eligible"] else "active_npr"] += 1
    audit = root / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "artifacts": {"inventory.parquet": sha256_file(inventory)},
                "script_sha256": {"jk_english_rows.py": "1" * 64},
                "parts": [
                    {
                        "filename": "EACA047PS0001.pdf",
                        "source_sha256": "0" * 64,
                        **counts,
                    }
                ],
            }
        )
    )
    return inventory, audit


@pytest.fixture
def source_rows() -> list[dict[str, object]]:
    base: dict[str, object] = {
        "filename": "EACA047PS0001.pdf",
        "id": "ABC1234567",
        "active": True,
        "assembly_eligible": True,
        "source_sha256": "0" * 64,
        "elector_name": "Alex Rivera",
        "name_candidate": "Alex Rivera",
        "name_issue": None,
        "relative_name": "Sam Rivera",
        "relative_candidate": "Sam Rivera",
        "relative_issue": None,
        "relative_type": "Father's Name",
        "house_no": "10",
        "age": "30",
        "sex_candidate": "Male",
    }
    variants = [
        {},
        {"elector_name": "Jamie Rivera"},
        {"elector_name": "Casey", "house_no": "0"},
        {
            "elector_name": "Taylor Reed",
            "relative_name": "Taylor Reed",
            "relative_type": "Self",
            "house_no": "20",
        },
        {
            "elector_name": None,
            "name_candidate": "Da�ta",
            "name_issue": "unverified_rendering",
            "house_no": "0",
        },
        {"active": False},
        {"assembly_eligible": False},
        {"elector_name": "Alex Rivera Stone", "relative_name": "Sam Stone"},
        {
            "elector_name": "Avery Reed",
            "relative_name": "Sam Reed",
            "relative_issue": "unverified_rendering",
            "house_no": "30",
        },
    ]
    return [
        {
            **base,
            **variant,
            "number": str(i),
            "entry_event_key": f"EACA047PS0001.pdf:3:{i}",
            "event_key": f"EACA047PS0001.pdf:3:{i}",
        }
        for i, variant in enumerate(variants, 1)
    ]


def test_cli_preserves_active_rows_and_excludes_unverified_evidence(
    tmp_path: Path, source_rows: list[dict[str, object]]
) -> None:
    inventory, audit = write_source(tmp_path / "source", source_rows)
    output = tmp_path / "output's"
    main(["resolve-jk-english", str(inventory), str(audit), str(output)])
    report = json.loads((output / "audit.json").read_text())
    rows = {
        r["source_number"]: r
        for r in pq.read_table(output / "surnames.parquet").to_pylist()
    }
    assert set(rows) == {"1", "2", "3", "4", "5", "8", "9"}
    assert report["counts"]["inactive_excluded"] == 1
    assert report["counts"]["active_npr_excluded"] == 1
    for number in ("1", "2"):
        assert rows[number]["surname_latin_normalized"] == "rivera"
        assert rows[number]["relationship_raw"] == "Father's Name"
    assert rows["4"]["relationship_raw"] == "Self"
    assert rows["4"]["abstained"]
    assert rows["5"]["abstained"]
    assert rows["5"]["name_source_raw"] == "Da�ta"
    assert rows["8"]["abstention_reason"] == "conflicting-evidence"
    assert rows["9"]["abstained"]
    assert all(r["surname_confidence"] is None for r in rows.values())
    assert all(r["surname_evidence"] != "position" for r in rows.values())
    assert rows["3"]["household_id"] is None
    prepared = pq.read_table(output / "electors.parquet").to_pylist()
    assert all(r["source_sha256"] == "0" * 64 and r["year"] == "2018" for r in prepared)
    for name, digest in report["artifacts"].items():
        assert sha256_file(output / name) == digest


@pytest.mark.parametrize(
    "failure", ["hash", "duplicate", "flag", "count", "source", "script"]
)
def test_bad_handoff_fails_atomically(
    tmp_path: Path, source_rows: list[dict[str, object]], failure: str
) -> None:
    if failure == "duplicate":
        source_rows.append(dict(source_rows[0]))
    if failure == "flag":
        source_rows[0]["active"] = None
    if failure == "source":
        source_rows[0]["source_sha256"] = "2" * 64
    inventory, audit = write_source(tmp_path / "source", source_rows)
    payload = json.loads(audit.read_text())
    if failure == "hash":
        payload["artifacts"]["inventory.parquet"] = "2" * 64
    if failure == "count":
        payload["parts"][0]["active_assembly"] += 1
    if failure == "script":
        payload["script_sha256"] = {}
    audit.write_text(json.dumps(payload))
    output = tmp_path / "failed"
    messages = {
        "hash": "SHA-256",
        "duplicate": "repeats an elector serial",
        "flag": "unresolved activity",
        "count": "disagrees with the source audit",
        "source": "source PDF hash",
        "script": "original English parser",
    }
    with pytest.raises(ValueError, match=messages[failure]):
        resolve_jk_english(inventory, audit, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".jk-english-*"))


def test_existing_destination_is_not_overwritten(tmp_path: Path) -> None:
    with pytest.raises(FileExistsError):
        resolve_jk_english(tmp_path / "missing", tmp_path / "missing", tmp_path)


def test_jk_does_not_pool_near_spellings(
    tmp_path: Path, source_rows: list[dict[str, object]]
) -> None:
    rows = source_rows[:2]
    rows[0].update(elector_name="Alex Begam", relative_name=None, relative_type="Self")
    rows[1].update(elector_name="Jamie Begum", relative_name=None, relative_type="Self")
    inventory, audit = write_source(tmp_path / "source", rows)
    output = tmp_path / "resolved"
    resolve_jk_english(inventory, audit, output)
    records = pq.read_table(output / "surnames.parquet").to_pylist()
    assert all(r["abstained"] for r in records)
