import gzip
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
import pytest

from upnaam.adapters.bihar_ration import (
    BIHAR_RATION_AGGREGATE_COLUMNS,
    BIHAR_RATION_AGGREGATE_REVISION,
    aggregate_bihar_ration_rows,
    write_bihar_ration_aggregate_audit,
)
from upnaam.cli import main


def _roster(*members: object) -> str:
    return json.dumps(list(members), ensure_ascii=False)


def test_aggregate_bihar_ration_rows_counts_members_and_households(
    tmp_path: Path,
) -> None:
    rows = [
        (
            "h1",
            4,
            _roster(
                {"सदस्य का नाम": "आशा देवी"},
                {"सदस्य का नाम": "गीता देवी"},
                {"सदस्य का नाम": "रानी यादव"},
            ),
        ),
        (
            "h2",
            3,
            _roster(
                {"सदस्य का नाम": "सीमा DEVI"},
                {"सदस्य का नाम": "मोहन यादव"},
                {"सदस्य का नाम": "मोहन"},
            ),
        ),
    ]

    result, report = aggregate_bihar_ration_rows(rows)

    assert list(result.columns) == BIHAR_RATION_AGGREGATE_COLUMNS
    assert result["surname_source_normalized"].tolist() == ["देवी", "यादव", "devi"]
    assert result["member_count"].tolist() == [2, 2, 1]
    devanagari_devi = result.loc[result["surname_source_normalized"] == "देवी"].iloc[0]
    assert devanagari_devi["surname_raw_mode"] == "देवी"
    assert devanagari_devi["household_count"] == 1
    yadav = result.loc[result["surname_source_normalized"] == "यादव"].iloc[0]
    assert yadav["household_count"] == 2
    assert report.source_households == 2
    assert report.declared_members == 7
    assert report.parsed_member_rows == 6
    assert report.selected_members == 5
    assert report.abstained_members == 1
    assert report.abstentions_by_reason == {"single-token-name": 1}
    assert report.member_count_mismatch_households == 1
    assert report.source_scan_complete
    assert set(result["aggregate_revision"]) == {BIHAR_RATION_AGGREGATE_REVISION}

    audit = tmp_path / "audit.json"
    write_bihar_ration_aggregate_audit(audit, report)
    assert json.loads(audit.read_text())["selected_members"] == 5


def test_aggregate_bihar_ration_rows_preserves_raw_variants_and_tie_rule() -> None:
    rows = [
        (
            "h1",
            3,
            _roster(
                {"सदस्य का नाम": "Asha DEVI"},
                {"सदस्य का नाम": "Gita devi"},
                {"सदस्य का नाम": "Sita Devi"},
            ),
        )
    ]

    result, _ = aggregate_bihar_ration_rows(rows)

    assert result.loc[0, "surname_source_normalized"] == "devi"
    assert result.loc[0, "surname_raw_mode"] == "DEVI"
    assert result.loc[0, "surname_raw_mode_count"] == 1
    assert result.loc[0, "raw_variant_count"] == 3


def test_aggregate_bihar_ration_rows_audits_invalid_source_rows() -> None:
    rows = [
        ("missing", None, None),
        ("malformed", 1, "{"),
        ("mapping", 1, json.dumps({"name": "not a list"})),
        ("members", 2, _roster("not a mapping", {"wrong field": "value"})),
    ]

    result, report = aggregate_bihar_ration_rows(rows, household_limit=4)

    assert result.empty
    assert report.missing_declared_member_count_households == 1
    assert report.malformed_json_households == 2
    assert report.non_list_roster_households == 1
    assert report.invalid_member_rows == 1
    assert report.valid_member_rows == 1
    assert report.abstentions_by_reason == {"missing-name": 1}
    assert not report.source_scan_complete
    assert report.household_limit == 4


def test_aggregate_bihar_ration_rows_rejects_invalid_contract() -> None:
    with pytest.raises(ValueError, match="exactly three"):
        aggregate_bihar_ration_rows([("household", "roster")])
    with pytest.raises(ValueError, match="at least one"):
        aggregate_bihar_ration_rows([], household_limit=0)


def test_empty_aggregate_preserves_schema_and_types() -> None:
    result, report = aggregate_bihar_ration_rows([])

    assert list(result.columns) == BIHAR_RATION_AGGREGATE_COLUMNS
    assert all(isinstance(dtype, pd.StringDtype) for dtype in result.dtypes[:2])
    assert str(result["member_count"].dtype) == "int64"
    assert report.distinct_surnames == 0


def test_cli_aggregates_a_compressed_bihar_database(tmp_path: Path) -> None:
    database = tmp_path / "ration.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "CREATE TABLE family_members_tables "
            "(id TEXT PRIMARY KEY, members_qty INTEGER, sub_table TEXT)"
        )
        connection.execute(
            "INSERT INTO family_members_tables VALUES (?, ?, ?)",
            (
                "h1",
                2,
                _roster(
                    {"सदस्य का नाम": "आशा देवी"},
                    {"सदस्य का नाम": "मोहन यादव"},
                ),
            ),
        )
        connection.commit()
    compressed = gzip.compress(database.read_bytes())
    midpoint = len(compressed) // 2
    parts = [tmp_path / "ration.sqlite.gz.001", tmp_path / "ration.sqlite.gz.002"]
    parts[0].write_bytes(compressed[:midpoint])
    parts[1].write_bytes(compressed[midpoint:])
    output = tmp_path / "counts.parquet"
    index = tmp_path / "ration.sqlite.gzidx"
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"

    main(
        [
            "aggregate-bihar-ration",
            str(output),
            "--part",
            str(parts[0]),
            "--part",
            str(parts[1]),
            "--index",
            str(index),
            "--audit",
            str(audit),
            "--manifest",
            str(manifest),
        ]
    )

    result = pd.read_parquet(output)
    assert result["surname_source_normalized"].tolist() == ["देवी", "यादव"]
    assert json.loads(audit.read_text())["source_scan_complete"]
    manifest_payload = json.loads(manifest.read_text())
    assert manifest_payload["stage"] == "bihar_ration_surname_counts"
    assert manifest_payload["row_counts"]["selected_members"] == 2
