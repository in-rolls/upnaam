import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from upnaam.adapters.punjab import (
    PUNJAB_OUTPUT_SCHEMA,
    RAW_COLUMNS,
    TRANSLITERATED_NATIVE_COLUMNS,
    build_punjab_elector_artifact,
    resolve_punjab_name_pair,
    write_punjab_summary,
)
from upnaam.cli import main
from upnaam.normalization import normalize_latin_token


def _roll_frame() -> pd.DataFrame:
    rows = []
    for index, name in enumerate(["ਰਵਿ ਸ਼ਰਮਾ", "ਦੇਵ ਰਾਜ", "ਹਰਪ੍ਰੀਤ ਸਿੰਘ", "ਕਮਲਾ"]):
        row = {column: f"{column}-{index}" for column in RAW_COLUMNS}
        row.update(
            {
                "id": "duplicate-source-id" if index < 2 else f"source-{index}",
                "number": str(index + 1),
                "elector_name": name,
                "father_or_husband_name": "ਰਾਮ ਸ਼ਰਮਾ",
                "relationship": "father",
                "house_no": "12",
                "age": "40",
                "sex": "Male",
                "part_no": "7",
                "year": "2018",
                "state": "Punjab",
                "filename": "roll.pdf",
            }
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=RAW_COLUMNS)


def _transliteration_frame(roll: pd.DataFrame) -> pd.DataFrame:
    frame = roll.loc[:, TRANSLITERATED_NATIVE_COLUMNS].copy()
    for column in TRANSLITERATED_NATIVE_COLUMNS:
        frame[f"{column}_transliterated"] = f"Latin {column}"
    frame["elector_name_transliterated"] = [
        "Ravi Sharma",
        "Dev Rāj",
        "Harpreet Kumar Singh",
        "Kamla",
    ]
    frame["father_or_husband_name_transliterated"] = "Ram Sharma"
    return frame


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, pd.DataFrame]:
    roll = _roll_frame()
    raw_path = tmp_path / "punjab.csv.gz"
    transliteration_path = tmp_path / "punjab.parquet"
    roll.to_csv(raw_path, index=False)
    _transliteration_frame(roll).to_parquet(transliteration_path, index=False)
    return raw_path, transliteration_path, roll


def test_normalize_latin_token_removes_diacritics() -> None:
    assert normalize_latin_token("Rāj") == "raj"
    assert normalize_latin_token("Manīshā") == "manisha"
    assert normalize_latin_token("123") is None


def test_resolve_punjab_name_pair_preserves_native_on_alignment_failure() -> None:
    resolved = resolve_punjab_name_pair("ਰਵਿ ਸ਼ਰਮਾ", "Ravi Sharma")
    assert resolved.surname_raw == "ਸ਼ਰਮਾ"
    assert resolved.surname_source_normalized == "ਸ਼ਰਮਾ"
    assert resolved.surname_latin_raw == "Sharma"
    assert resolved.surname_latin_normalized == "sharma"
    assert resolved.transliteration_status == "aligned"

    mismatch = resolve_punjab_name_pair("ਹਰਪ੍ਰੀਤ ਸਿੰਘ", "Harpreet Kumar Singh")
    assert mismatch.surname_raw == "ਸਿੰਘ"
    assert mismatch.surname_latin_raw is None
    assert mismatch.surname_latin_normalized is None
    assert not mismatch.abstained
    assert mismatch.transliteration_status == "token-count-mismatch"

    single = resolve_punjab_name_pair("ਕਮਲਾ", "Kamla")
    assert single.abstained
    assert single.abstention_reason == "single-token-name"
    assert single.transliteration_status == "no-surname-selected"


def test_build_punjab_artifact_preserves_every_source_row(tmp_path: Path) -> None:
    raw_path, transliteration_path, roll = _write_inputs(tmp_path)
    output = tmp_path / "resolved.parquet"
    report = build_punjab_elector_artifact(
        raw_path, transliteration_path, output, batch_size=2
    )
    frame = pd.read_parquet(output)

    assert report.rows == len(roll)
    assert report.abstention_reasons == {"single-token-name": 1}
    assert report.transliteration_statuses == {
        "aligned": 2,
        "token-count-mismatch": 1,
        "no-surname-selected": 1,
    }
    assert report.by_sex["male"]["rows"] == 4
    assert report.by_relationship["father"]["native_resolved"] == 3
    assert report.top_surnames == (("sharma", 1), ("raj", 1))
    assert frame["source_row"].tolist() == [0, 1, 2, 3]
    assert frame["elector_id"].tolist() == [
        "muegdt-v25-punjab:0",
        "muegdt-v25-punjab:1",
        "muegdt-v25-punjab:2",
        "muegdt-v25-punjab:3",
    ]
    assert frame.loc[0, "source_elector_id"] == frame.loc[1, "source_elector_id"]
    assert frame.loc[0, "surname_raw"] == "ਸ਼ਰਮਾ"
    assert frame.loc[0, "surname_source_normalized"] == "ਸ਼ਰਮਾ"
    assert frame.loc[1, "surname_latin_raw"] == "Rāj"
    assert frame.loc[1, "surname_latin_normalized"] == "raj"
    assert frame.loc[1, "surname_canonical"] == "raj"
    assert frame.loc[1, "canonicalization_status"] == "identity_unmapped"
    assert frame.loc[2, "surname_raw"] == "ਸਿੰਘ"
    assert pd.isna(frame.loc[2, "surname_latin_normalized"])
    assert frame.loc[2, "canonicalization_status"] == "normalization_unavailable"
    assert frame.loc[3, "abstention_reason"] == "single-token-name"
    assert frame.loc[3, "canonicalization_status"] == "not_applicable"
    assert pq.ParquetFile(output).schema_arrow == PUNJAB_OUTPUT_SCHEMA

    summary = tmp_path / "summary.csv"
    write_punjab_summary(summary, report)
    summary_frame = pd.read_csv(summary)
    assert summary_frame.loc[0, "rows"] == 4
    assert summary_frame.loc[1, "value"] == "male"
    assert summary_frame.loc[1, "native_resolved"] == 3


def test_punjab_cli_writes_optional_audits(tmp_path: Path) -> None:
    raw_path, transliteration_path, _ = _write_inputs(tmp_path)
    output = tmp_path / "cli.parquet"
    audit = tmp_path / "audit.json"
    summary = tmp_path / "summary.csv"
    main(
        [
            "resolve-punjab",
            str(raw_path),
            str(transliteration_path),
            str(output),
            "--audit",
            str(audit),
            "--summary",
            str(summary),
            "--batch-size",
            "2",
        ]
    )
    assert json.loads(audit.read_text())["rows"] == 4
    assert pd.read_csv(summary).loc[0, "rows"] == 4


def test_build_punjab_artifact_rejects_native_mismatch(tmp_path: Path) -> None:
    raw_path, transliteration_path, roll = _write_inputs(tmp_path)
    companion = _transliteration_frame(roll)
    companion.loc[2, "elector_name"] = "ਵੱਖਰਾ ਨਾਮ"
    companion.to_parquet(transliteration_path, index=False)

    with pytest.raises(ValueError, match="native-field mismatch at source_row 2"):
        build_punjab_elector_artifact(
            raw_path, transliteration_path, tmp_path / "resolved.parquet", batch_size=2
        )
    assert not (tmp_path / "resolved.parquet").exists()
    assert not (tmp_path / "resolved.parquet.tmp").exists()


def test_build_punjab_artifact_rejects_row_count_mismatch(tmp_path: Path) -> None:
    raw_path, transliteration_path, roll = _write_inputs(tmp_path)
    _transliteration_frame(roll).iloc[:-1].to_parquet(transliteration_path, index=False)

    with pytest.raises(ValueError, match=r"different rows|batch lengths differ"):
        build_punjab_elector_artifact(
            raw_path, transliteration_path, tmp_path / "resolved.parquet", batch_size=2
        )
    assert not (tmp_path / "resolved.parquet").exists()
    assert not (tmp_path / "resolved.parquet.tmp").exists()
