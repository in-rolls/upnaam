import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from upnaam.adapters.rajasthan import (
    RAJASTHAN_EVIDENCE_SCHEMA,
    RAJASTHAN_RECONCILIATION_CONTEXT,
    build_rajasthan_surname_evidence,
    write_rajasthan_evidence_audit,
)
from upnaam.cli import main


def _links() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": [
                "rajasthan_ration",
                "rajasthan_ration",
                "rajasthan_ration",
                "bihar_land",
            ],
            "link_tier": ["T1", "T2", "T2", "T2"],
            "roll_name_raw": ["रवि शर्मा", "मोहन जाधब", "कमला", "राम राय"],
            "external_name_raw": [
                "रवि शर्मा",
                "मोहन जाधव",
                "कमला",
                "राम राय",
            ],
        }
    )


def test_rajasthan_evidence_is_surname_only_and_aggregate(tmp_path: Path) -> None:
    links = tmp_path / "links.parquet"
    output = tmp_path / "evidence.parquet"
    audit = tmp_path / "audit.json"
    _links().to_parquet(links, index=False)

    report = build_rajasthan_surname_evidence(links, output, batch_size=2)
    write_rajasthan_evidence_audit(audit, report)
    frame = pd.read_parquet(output)

    assert report.accepted_links == 3
    assert report.surname_pairs == 2
    assert report.skipped_by_reason == {"roll_surname_unresolved": 1}
    assert frame[["observed_form", "canonical_label", "support"]].to_dict(
        orient="records"
    ) == [
        {"observed_form": "जाधब", "canonical_label": "जाधव", "support": 1},
        {"observed_form": "शर्मा", "canonical_label": "शर्मा", "support": 1},
    ]
    assert set(frame["context"]) == {RAJASTHAN_RECONCILIATION_CONTEXT}
    assert pq.ParquetFile(output).schema_arrow == RAJASTHAN_EVIDENCE_SCHEMA
    assert json.loads(audit.read_text())["distinct_observed_forms"] == 2


def test_rajasthan_evidence_cli_writes_audit(tmp_path: Path) -> None:
    links = tmp_path / "links.parquet"
    output = tmp_path / "evidence.parquet"
    audit = tmp_path / "audit.json"
    _links().to_parquet(links, index=False)
    main(
        [
            "evidence-rajasthan",
            str(links),
            str(output),
            "--audit",
            str(audit),
            "--batch-size",
            "2",
        ]
    )
    assert json.loads(audit.read_text())["directed_evidence_rows"] == 2


def test_rajasthan_evidence_rejects_contract_violations(tmp_path: Path) -> None:
    missing = tmp_path / "missing.parquet"
    pd.DataFrame({"source": ["rajasthan_ration"]}).to_parquet(missing, index=False)
    with pytest.raises(ValueError, match="missing columns"):
        build_rajasthan_surname_evidence(missing, tmp_path / "out.parquet")

    invalid = tmp_path / "invalid.parquet"
    frame = _links().iloc[[0]].assign(link_tier="T3")
    frame.to_parquet(invalid, index=False)
    with pytest.raises(ValueError, match="unsupported"):
        build_rajasthan_surname_evidence(invalid, tmp_path / "out.parquet")
