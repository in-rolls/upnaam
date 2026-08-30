import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from upnaam.adapters.bihar import (
    BIHAR_REFERENCE_SCHEMA,
    build_bihar_land_reference_labels,
    write_bihar_reference_audit,
    write_bihar_reference_summary,
)
from upnaam.cli import main


def _links() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": ["bihar_land"] * 5,
            "link_tier": ["exact_name_and_relative"] * 5,
            "link_id": [f"bihar_land:a{index}" for index in range(5)],
            "roll_id": [f"v{index}" for index in range(5)],
            "external_id": [f"a{index}" for index in range(5)],
            "roll_name_raw": [
                "मथुरा साव",
                "अशोक कुमार सिन्हा",
                "श्री देवी",
                "कमला",
                "प्रेमलता कुमारी",
            ],
            "external_name_raw": [
                "मथुरा साव",
                "अशोक कुमार सिन्‍हा",
                "कुमारी देवी",
                "कमला",
                "कुमारी प्रेमलता",
            ],
            "relation_type": ["father", "father", "husband", "father", "father"],
            "sex": ["male", "male", "female", "female", None],
            "name_exact_upstream": [True] * 5,
            "edit_learning_eligible": [False] * 5,
            "omission_eligible": [False] * 5,
        }
    )


def test_bihar_land_labels_prefer_land_and_preserve_conflicts(tmp_path: Path) -> None:
    links = tmp_path / "links.parquet"
    output = tmp_path / "labels.parquet"
    audit = tmp_path / "audit.json"
    summary = tmp_path / "summary.csv"
    _links().to_parquet(links, index=False)

    report = build_bihar_land_reference_labels(links, output, batch_size=2)
    write_bihar_reference_audit(audit, report)
    write_bihar_reference_summary(summary, report)
    labels = pd.read_parquet(output)

    assert report.source_links == 5
    assert report.accepted_labels == 3
    assert report.agreement_labels == 2
    assert report.land_added_labels == 1
    assert report.abstained_labels == 1
    assert report.excluded_conflicts == 1
    assert report.full_name_normalized_agreements == 3
    assert report.distinct_reference_surnames == 3
    assert labels["reference_label_status"].tolist() == [
        "accepted",
        "accepted",
        "accepted",
        "abstained",
        "excluded",
    ]
    assert labels.loc[2, "reference_surname_raw"] == "देवी"
    assert labels.loc[2, "reference_label_reason"] == (
        "land_record_adds_reference_surname"
    )
    assert pd.isna(labels.loc[3, "reference_surname_raw"])
    assert pd.isna(labels.loc[4, "reference_surname_raw"])
    assert labels.loc[4, "land_surname_raw"] == "प्रेमलता"
    assert pq.ParquetFile(output).schema_arrow == BIHAR_REFERENCE_SCHEMA
    assert json.loads(audit.read_text())["accepted_labels"] == 3
    assert pd.read_csv(summary).loc[0, "rows"] == 5


def test_bihar_land_labels_cli_writes_outputs(tmp_path: Path) -> None:
    links = tmp_path / "links.parquet"
    output = tmp_path / "labels.parquet"
    audit = tmp_path / "audit.json"
    summary = tmp_path / "summary.csv"
    manifest = tmp_path / "manifest.json"
    _links().to_parquet(links, index=False)
    main(
        [
            "labels-bihar-land",
            str(links),
            str(output),
            "--audit",
            str(audit),
            "--summary",
            str(summary),
            "--manifest",
            str(manifest),
            "--batch-size",
            "2",
        ]
    )
    assert len(pd.read_parquet(output)) == 5
    assert json.loads(audit.read_text())["excluded_conflicts"] == 1
    manifest_payload = json.loads(manifest.read_text())
    assert manifest_payload["stage"] == "bihar_land_reference_labels"
    assert manifest_payload["row_counts"]["accepted_labels"] == 3
    assert manifest_payload["parameters"]["surname_rule"] == "last_eligible_token"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"source": "rajasthan_ration"}, "another source"),
        ({"link_tier": "T1"}, "another link tier"),
        ({"name_exact_upstream": False}, "eligibility flags"),
    ],
)
def test_bihar_land_labels_reject_contract_violations(
    tmp_path: Path, change: dict[str, object], message: str
) -> None:
    links = tmp_path / "links.parquet"
    frame = _links().iloc[[0]].assign(**change)
    frame.to_parquet(links, index=False)
    with pytest.raises(ValueError, match=message):
        build_bihar_land_reference_labels(links, tmp_path / "labels.parquet")


def test_bihar_land_labels_reject_missing_columns_and_duplicate_keys(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.parquet"
    pd.DataFrame({"source": ["bihar_land"]}).to_parquet(missing, index=False)
    with pytest.raises(ValueError, match="missing columns"):
        build_bihar_land_reference_labels(missing, tmp_path / "labels.parquet")

    duplicate = tmp_path / "duplicate.parquet"
    frame = pd.concat([_links().iloc[[0]], _links().iloc[[0]]], ignore_index=True)
    frame.to_parquet(duplicate, index=False)
    with pytest.raises(ValueError, match="one-to-one"):
        build_bihar_land_reference_labels(duplicate, tmp_path / "labels.parquet")

    with pytest.raises(ValueError, match="batch_size"):
        build_bihar_land_reference_labels(
            duplicate, tmp_path / "labels.parquet", batch_size=0
        )
