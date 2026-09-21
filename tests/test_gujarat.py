import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from upnaam.adapters.gujarat import (
    build_gujarat_elector_artifact,
    resolve_gujarat_name,
    write_gujarat_audit,
)


def test_gujarat_selects_the_first_written_token_and_maps_it():
    result = resolve_gujarat_name("પટેલ રમિલાબેન", {"પટેલ": "patel"}.get)

    assert result.surname_raw == "પટેલ"
    assert result.surname_latin_normalized == "patel"
    assert result.transliteration_status == "mapped"
    assert not result.abstained


def test_gujarat_preserves_native_selection_on_a_lookup_miss():
    result = resolve_gujarat_name("પરમાર રીના", {}.get)

    assert result.surname_raw == "પરમાર"
    assert result.surname_latin_normalized is None
    assert result.transliteration_status == "lookup-miss"
    assert not result.abstained


def test_gujarat_abstains_on_a_single_token_name():
    result = resolve_gujarat_name("રમિલાબેન", {"રમિલાબેન": "ramilaben"}.get)

    assert result.surname_raw is None
    assert result.abstention_reason == "single-token-name"
    assert result.transliteration_status == "no-surname-selected"
    assert result.abstained


def test_gujarat_builder_preserves_source_identity_and_writes_an_audit(
    tmp_path: Path,
):
    source = tmp_path / "records.parquet"
    output = tmp_path / "surnames.parquet"
    audit = tmp_path / "audit.json"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "record_id": "gujarat-2017:part:1:2",
                    "source_filename": "NORMAL_AC001N0010001.pdf",
                    "assembly_constituency": 1,
                    "part_number": 1,
                    "source_page": 2,
                    "serial_number": 1,
                    "epic_id": "ABC1234567",
                    "elector_name_native": "પટેલ રમિલાબેન",
                    "relative_name_native": "પટેલ રમેશ",
                    "relationship": "father",
                    "house_number": "12",
                },
                {
                    "record_id": "gujarat-2017:part:2:2",
                    "source_filename": "NORMAL_AC001N0010001.pdf",
                    "assembly_constituency": 1,
                    "part_number": 1,
                    "source_page": 2,
                    "serial_number": 2,
                    "epic_id": "ABC1234568",
                    "elector_name_native": "રીના",
                    "relative_name_native": "પટેલ રમેશ",
                    "relationship": "father",
                    "house_number": "12",
                },
            ]
        ),
        source,
    )

    report = build_gujarat_elector_artifact(
        source,
        output,
        romanize_token={"પટેલ": "patel"}.get,
        transliteration_revision="sha256:fixture",
        batch_size=1,
    )
    write_gujarat_audit(audit, report)

    rows = pq.read_table(output).to_pylist()
    assert rows[0]["record_id"] == "gujarat-2017:part:1:2"
    assert rows[0]["surname_raw"] == "પટેલ"
    assert rows[0]["surname_latin_normalized"] == "patel"
    assert rows[0]["surname_position"] == "first"
    assert rows[0]["surname_evidence"] == "position"
    assert rows[1]["abstention_reason"] == "single-token-name"
    payload = json.loads(audit.read_text())
    assert payload["rows"] == 2
    assert payload["selected_native"] == 1
    assert payload["mapped_latin"] == 1
