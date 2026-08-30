import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from upnaam.adapters.bihar_land_inference import (
    BIHAR_LAND_INFERENCE_REVISION,
    BIHAR_LAND_INFERRED_SCHEMA,
    BIHAR_LAND_RECORD_SUFFIXES,
    infer_bihar_land_surname_counts,
)
from upnaam.cli import main


def _names() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name_of_ryot": pd.Series(
                [
                    "किशोर यादव",
                    "मोहन यादव वगैरह",
                    "गीता सिंह अन्य",
                    "राम वगै0",
                    "सीमा वगैराह",
                    "मोहन",
                    None,
                ],
                dtype="string",
            )
        }
    )


def test_bihar_land_inference_uses_only_exact_record_suffixes(
    tmp_path: Path,
) -> None:
    assert (
        frozenset(
            {
                "अन्य",
                "बगेरह",
                "बगैरह",
                "वगेरह",
                "वगै",
                "वगै0",
                "वगैरह",
                "वगैरा",
                "वैगरह",
                "वोगैरह",
            }
        )
        == BIHAR_LAND_RECORD_SUFFIXES
    )
    source = tmp_path / "names.parquet"
    output = tmp_path / "inferred.parquet"
    _names().to_parquet(source, index=False)

    report = infer_bihar_land_surname_counts(source, output, batch_size=2)
    result = pd.read_parquet(output).set_index("surname_inferred_normalized")

    assert result.loc["यादव", "distinct_full_name_count"] == 2
    assert result.loc["यादव", "written_final_token_count"] == 1
    assert result.loc["यादव", "record_suffix_adjusted_count"] == 1
    assert result.loc["सिंह", "record_suffix_adjusted_count"] == 1
    assert result.loc["राम", "record_suffix_adjusted_count"] == 1
    assert result.loc["वगैराह", "written_final_token_count"] == 1
    assert report.record_suffix_adjusted_names == 3
    assert report.adjustments_by_suffix == {"अन्य": 1, "वगै0": 1, "वगैरह": 1}
    assert report.abstentions_by_reason == {
        "missing-name": 1,
        "single-token-name": 1,
    }
    assert pq.ParquetFile(output).schema_arrow == BIHAR_LAND_INFERRED_SCHEMA
    assert set(result["inference_revision"]) == {BIHAR_LAND_INFERENCE_REVISION}


def test_bihar_land_inference_cli_writes_audit_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "names.parquet"
    output = tmp_path / "inferred.parquet"
    audit = tmp_path / "audit.json"
    manifest = tmp_path / "manifest.json"
    _names().to_parquet(source, index=False)

    main(
        [
            "infer-bihar-land",
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

    assert json.loads(audit.read_text())["record_suffix_adjusted_names"] == 3
    payload = json.loads(manifest.read_text())
    assert payload["stage"] == "bihar_land_inferred_surname_counts"
    assert payload["parameters"]["record_suffix_matching"] == ("exact_normalized_token")
    assert set(payload["parameters"]["record_suffixes"]) == (BIHAR_LAND_RECORD_SUFFIXES)


def test_bihar_land_inference_rejects_invalid_contract(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.parquet"
    pd.DataFrame({"name_of_ryot": ["आशा देवी", "आशा देवी"]}).to_parquet(
        duplicate, index=False
    )
    with pytest.raises(ValueError, match="distinct"):
        infer_bihar_land_surname_counts(duplicate, tmp_path / "inferred.parquet")

    missing = tmp_path / "missing.parquet"
    pd.DataFrame({"other": ["आशा देवी"]}).to_parquet(missing, index=False)
    with pytest.raises(ValueError, match="missing column"):
        infer_bihar_land_surname_counts(missing, tmp_path / "inferred.parquet")

    numeric = tmp_path / "numeric.parquet"
    pd.DataFrame({"name_of_ryot": [1]}).to_parquet(numeric, index=False)
    with pytest.raises(ValueError, match="string type"):
        infer_bihar_land_surname_counts(numeric, tmp_path / "inferred.parquet")

    with pytest.raises(ValueError, match="batch_size"):
        infer_bihar_land_surname_counts(
            missing, tmp_path / "inferred.parquet", batch_size=0
        )
