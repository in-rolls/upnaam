import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from upnaam.adapters.rajasthan_reference import (
    RAJASTHAN_REFERENCE_SCHEMA,
    build_rajasthan_ration_reference_labels,
    write_rajasthan_reference_audit,
    write_rajasthan_reference_summary,
)
from upnaam.cli import main


def _links() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": ["rajasthan_ration"] * 6,
            "link_tier": ["T1", "T2", "T2", "T1", "T1", "T2"],
            "link_id": [
                "rajasthan_ration:a:1",
                "rajasthan_ration:b:1",
                "rajasthan_ration:c:1",
                "rajasthan_ration:d:1",
                "rajasthan_ration:e:1",
                "rajasthan_ration:e:1",
            ],
            "roll_id": [f"v{index}" for index in range(6)],
            "external_id": ["a:1", "b:1", "c:1", "d:1", "e:1", "e:1"],
            "roll_name_raw": [
                "मथुरा साव",
                "सीताराम",
                "सरोज केंवर",
                "कमला",
                "ईश्वर सिंह",
                "ईश्वर सिह",
            ],
            "external_name_raw": [
                "मथुरा साव",
                "सीता राम",
                "सरोज कंवर",
                "कमला",
                "ईश्वर सिंह",
                "ईश्वर सिंह",
            ],
            "relation_type": ["father", "father", "husband", "father", None, None],
            "sex": ["m", "m", "f", "f", "m", None],
            "name_exact_upstream": [True, False, False, True, True, False],
        }
    )


def test_rajasthan_reference_labels_apply_gold_assumption_and_exclusions(
    tmp_path: Path,
) -> None:
    links = tmp_path / "links.parquet"
    output = tmp_path / "labels.parquet"
    audit = tmp_path / "audit.json"
    summary = tmp_path / "summary.csv"
    _links().to_parquet(links, index=False)

    report = build_rajasthan_ration_reference_labels(links, output, batch_size=2)
    write_rajasthan_reference_audit(audit, report)
    write_rajasthan_reference_summary(summary, report)
    labels = pd.read_parquet(output)

    assert report.source_links == 6
    assert report.unique_ration_members == 5
    assert report.duplicated_ration_members == 1
    assert report.accepted_labels == 3
    assert report.abstained_labels == 1
    assert report.excluded_nonunique_links == 2
    assert report.surname_agreements == 1
    assert report.surname_conflicts == 1
    assert report.ration_added_labels == 1
    assert report.distinct_reference_surnames == 3
    assert labels["reference_label_status"].tolist() == [
        "accepted",
        "accepted",
        "accepted",
        "abstained",
        "excluded",
        "excluded",
    ]
    assert labels.loc[1, "reference_surname_raw"] == "राम"
    assert pd.isna(labels.loc[1, "roll_surname_raw"])
    assert labels.loc[2, "reference_surname_raw"] == "कंवर"
    assert not bool(labels.loc[2, "selected_surname_normalized_agreement"])
    assert labels.loc[4, "reference_label_reason"] == ("nonunique_ration_member_link")
    assert labels.loc[4, "ration_member_link_count"] == 2
    assert pd.isna(labels.loc[4, "reference_surname_raw"])
    assert pq.ParquetFile(output).schema_arrow == RAJASTHAN_REFERENCE_SCHEMA
    assert json.loads(audit.read_text())["accepted_labels"] == 3
    assert pd.read_csv(summary).loc[0, "rows"] == 6


def test_rajasthan_reference_cli_writes_manifest(tmp_path: Path) -> None:
    links = tmp_path / "links.parquet"
    output = tmp_path / "labels.parquet"
    audit = tmp_path / "audit.json"
    summary = tmp_path / "summary.csv"
    manifest = tmp_path / "manifest.json"
    _links().to_parquet(links, index=False)

    main(
        [
            "labels-rajasthan-ration",
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

    payload = json.loads(manifest.read_text())
    assert payload["stage"] == "rajasthan_ration_reference_labels"
    assert payload["row_counts"]["accepted_labels"] == 3
    assert payload["parameters"]["reference_standard"] == "provisional_gold"
    assert payload["parameters"]["nonunique_ration_member_policy"] == (
        "exclude_all_links"
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"source": "bihar_land"}, "another source"),
        ({"link_tier": "T3"}, "another link tier"),
        ({"name_exact_upstream": "yes"}, "must be boolean"),
    ],
)
def test_rajasthan_reference_rejects_contract_violations(
    tmp_path: Path, change: dict[str, object], message: str
) -> None:
    links = tmp_path / "links.parquet"
    _links().iloc[[0]].assign(**change).to_parquet(links, index=False)
    with pytest.raises(ValueError, match=message):
        build_rajasthan_ration_reference_labels(links, tmp_path / "labels.parquet")


def test_rajasthan_reference_rejects_missing_columns_duplicate_roll_and_batch(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.parquet"
    pd.DataFrame({"source": ["rajasthan_ration"]}).to_parquet(missing, index=False)
    with pytest.raises(ValueError, match="missing columns"):
        build_rajasthan_ration_reference_labels(missing, tmp_path / "labels.parquet")

    duplicate = tmp_path / "duplicate.parquet"
    pd.concat([_links().iloc[[0]], _links().iloc[[0]]], ignore_index=True).to_parquet(
        duplicate, index=False
    )
    with pytest.raises(ValueError, match="roll IDs must be unique"):
        build_rajasthan_ration_reference_labels(duplicate, tmp_path / "labels.parquet")

    with pytest.raises(ValueError, match="batch_size"):
        build_rajasthan_ration_reference_labels(
            duplicate, tmp_path / "labels.parquet", batch_size=0
        )
