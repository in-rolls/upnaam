import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from upnaam.adapters.bihar_land_counts import (
    BIHAR_LAND_AGGREGATE_REVISION,
    BIHAR_LAND_AGGREGATE_SCHEMA,
    build_bihar_land_surname_counts,
)
from upnaam.cli import main


def _names() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name_of_ryot": pd.Series(
                [
                    "आशा देवी",
                    "गीता देवी",
                    "मोहन यादव",
                    "राम सिंह",
                    "मोहन",
                    None,
                ],
                dtype="string",
            )
        }
    )


def test_bihar_land_counts_distinct_written_name_strings(tmp_path: Path) -> None:
    source = tmp_path / "names.parquet"
    output = tmp_path / "counts.parquet"
    _names().to_parquet(source, index=False)

    report = build_bihar_land_surname_counts(source, output, batch_size=2)
    result = pd.read_parquet(output)

    assert result["surname_source_normalized"].tolist() == [
        "देवी",
        "यादव",
        "सिंह",
    ]
    assert result["distinct_full_name_count"].tolist() == [2, 1, 1]
    assert report.source_rows == 6
    assert report.nonnull_name_rows == 5
    assert report.selected_names == 4
    assert report.abstained_names == 2
    assert report.abstentions_by_reason == {
        "missing-name": 1,
        "single-token-name": 1,
    }
    assert pq.ParquetFile(output).schema_arrow == BIHAR_LAND_AGGREGATE_SCHEMA
    assert set(result["aggregate_revision"]) == {BIHAR_LAND_AGGREGATE_REVISION}


def test_bihar_land_counts_cli_writes_audit_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "names.parquet"
    output = tmp_path / "counts.parquet"
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    _names().to_parquet(source, index=False)

    main(
        [
            "aggregate-bihar-land",
            str(source),
            str(output),
            "--audit",
            str(audit),
            "--manifest",
            str(manifest),
            "--batch-size",
            "2",
        ]
    )

    assert json.loads(audit.read_text())["distinct_surnames"] == 3
    payload = json.loads(manifest.read_text())
    assert payload["stage"] == "bihar_land_surname_counts"
    assert payload["parameters"]["input_unit"] == ("distinct_official_full_name_string")


def test_bihar_land_counts_rejects_invalid_contract(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.parquet"
    pd.DataFrame({"name_of_ryot": ["आशा देवी", "आशा देवी"]}).to_parquet(
        duplicate, index=False
    )
    with pytest.raises(ValueError, match="distinct"):
        build_bihar_land_surname_counts(duplicate, tmp_path / "counts.parquet")

    missing = tmp_path / "missing.parquet"
    pd.DataFrame({"other": ["आशा देवी"]}).to_parquet(missing, index=False)
    with pytest.raises(ValueError, match="missing column"):
        build_bihar_land_surname_counts(missing, tmp_path / "counts.parquet")

    numeric = tmp_path / "numeric.parquet"
    pd.DataFrame({"name_of_ryot": [1]}).to_parquet(numeric, index=False)
    with pytest.raises(ValueError, match="string type"):
        build_bihar_land_surname_counts(numeric, tmp_path / "counts.parquet")

    with pytest.raises(ValueError, match="batch_size"):
        build_bihar_land_surname_counts(
            missing, tmp_path / "counts.parquet", batch_size=0
        )
