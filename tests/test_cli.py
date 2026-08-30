import json
from pathlib import Path

import pandas as pd
import pytest

from upnaam.cli import main


def test_cli_normalize_select_and_resolve(tmp_path: Path) -> None:
    names = tmp_path / "names.csv"
    normalized = tmp_path / "normalized.parquet"
    selected = tmp_path / "selected.parquet"
    resolved = tmp_path / "resolved.parquet"
    pd.DataFrame(
        {
            "elector_id": ["roll:1", "roll:2"],
            "state": ["bihar", "maharashtra"],
            "name": [" Poorna  Devi ", "Patil Ashwini"],
        }
    ).to_csv(names, index=False)

    main(["normalize", str(names), str(normalized)])
    main(["select", str(normalized), str(selected)])
    main(["resolve", str(names), str(resolved)])

    normalized_frame = pd.read_parquet(normalized)
    selected_frame = pd.read_parquet(selected)
    resolved_frame = pd.read_parquet(resolved)
    assert normalized_frame["name_normalized"].tolist() == [
        "poorna devi",
        "patil ashwini",
    ]
    assert selected_frame["surname_first_normalized"].tolist() == [
        "poorna",
        "patil",
    ]
    assert selected_frame["surname_last_normalized"].tolist() == ["devi", "ashwini"]
    assert resolved_frame["surname_canonical"].tolist() == ["devi", "patil"]


def test_cli_reconciliation_rank_decide_and_apply(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.parquet"
    candidates = tmp_path / "candidates.parquet"
    decisions = tmp_path / "decisions.parquet"
    audit = tmp_path / "decisions.json"
    records = tmp_path / "records.parquet"
    canonical = tmp_path / "canonical.parquet"
    pd.DataFrame(
        {
            "observed_form": ["jadhab", "jadhav", "sarma", "sarma"],
            "context": ["global"] * 4,
            "canonical_id": ["jadhav", "jadhav", "sarma", "sharma"],
            "canonical_label": ["jadhav", "jadhav", "sarma", "sharma"],
            "support": [3, 10, 3, 3],
            "similarity": [0.83, 1.0, 1.0, 0.9],
            "source": ["ration:T2", "ration:T1", "ration:T1", "ration:T2"],
            "evidence_tier": ["linked_record"] * 4,
        }
    ).to_parquet(evidence, index=False)

    main(["reconcile", "rank", str(evidence), str(candidates)])
    main(
        [
            "reconcile",
            "decide",
            str(candidates),
            str(decisions),
            "--audit",
            str(audit),
        ]
    )
    pd.DataFrame(
        {"surname_latin_normalized": ["jadhab", "jadhav", "sarma", "sharma"]}
    ).to_parquet(records, index=False)
    main(
        [
            "reconcile",
            "apply",
            str(records),
            str(canonical),
            str(decisions),
        ]
    )
    result = pd.read_parquet(canonical)
    assert result["surname_canonical"].tolist()[:2] == ["jadhav", "jadhav"]
    assert pd.isna(result.loc[2, "surname_canonical"])
    assert result.loc[3, "surname_canonical"] == "sharma"
    assert result["canonicalization_status"].tolist() == [
        "variant_mapped",
        "canonical_identity",
        "ambiguous",
        "identity_unmapped",
    ]
    assert json.loads(audit.read_text())["accepted_variant"] == 1


def test_cli_proposes_variant_candidates_without_mapping(tmp_path: Path) -> None:
    frequencies = tmp_path / "frequencies.parquet"
    candidates = tmp_path / "candidates.parquet"
    audit = tmp_path / "candidates.json"
    manifest = tmp_path / "manifest.json"
    pd.DataFrame(
        {
            "surname_source_normalized": ["jadhab", "jadhav", "sharma", "noise"],
            "member_count": [12, 100, 50, 1],
        }
    ).to_parquet(frequencies, index=False)

    main(
        [
            "reconcile",
            "propose",
            str(frequencies),
            str(candidates),
            "--audit",
            str(audit),
            "--manifest",
            str(manifest),
        ]
    )

    result = pd.read_parquet(candidates)
    assert result[["left", "right"]].to_dict(orient="records") == [
        {"left": "jadhab", "right": "jadhav"}
    ]
    assert result.loc[0, "candidate_reason"] == "edit_distance_gate"
    assert json.loads(audit.read_text())["eligible_forms"] == 3
    assert json.loads(manifest.read_text())["stage"] == "variant_candidate_proposals"


def test_cli_writes_typed_empty_variant_candidates(tmp_path: Path) -> None:
    frequencies = tmp_path / "frequencies.parquet"
    candidates = tmp_path / "candidates.parquet"
    pd.DataFrame(
        {
            "surname_source_normalized": ["sharma"],
            "member_count": [100],
        }
    ).to_parquet(frequencies, index=False)

    main(["reconcile", "propose", str(frequencies), str(candidates)])

    result = pd.read_parquet(candidates)
    assert result.empty
    assert result.dtypes.astype(str).to_dict() == {
        "left": "string",
        "right": "string",
        "distance": "int64",
        "similarity": "float64",
        "left_frequency": "int64",
        "right_frequency": "int64",
        "candidate_reason": "string",
        "candidate_revision": "string",
    }


def test_cli_empty_reconciliation_artifacts_keep_their_schema(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.parquet"
    candidates = tmp_path / "candidates.parquet"
    decisions = tmp_path / "decisions.parquet"
    pd.DataFrame(
        columns=[
            "observed_form",
            "context",
            "canonical_id",
            "canonical_label",
            "support",
            "similarity",
            "source",
            "evidence_tier",
        ]
    ).to_parquet(evidence, index=False)
    main(["reconcile", "rank", str(evidence), str(candidates)])
    main(["reconcile", "decide", str(candidates), str(decisions)])
    assert list(pd.read_parquet(decisions).columns) == [
        "observed_form",
        "context",
        "canonical_id",
        "canonical_label",
        "status",
        "reason",
        "candidate_count",
        "eligible_candidate_count",
        "top_support",
        "runner_up_support",
        "min_support_threshold",
        "min_similarity_threshold",
        "reconciliation_revision",
    ]


def test_cli_reconciliation_rejects_null_evidence_keys(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.parquet"
    pd.DataFrame(
        {
            "observed_form": [None],
            "context": ["global"],
            "canonical_id": ["anchor:rai"],
            "canonical_label": ["rai"],
            "support": [2],
            "similarity": [1.0],
            "source": ["ration:T1"],
            "evidence_tier": ["linked_record"],
        }
    ).to_parquet(evidence, index=False)
    with pytest.raises(ValueError, match="observed_form"):
        main(
            [
                "reconcile",
                "rank",
                str(evidence),
                str(tmp_path / "candidates.parquet"),
            ]
        )
