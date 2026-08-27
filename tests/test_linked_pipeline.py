import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from upnaam.linked_stages import (
    align_link_table,
    build_variant_table,
    evaluate_outputs,
    learn_edit_artifact,
    resolve_family_surnames,
    resolve_linked_surnames,
)


def _write_links(path: Path) -> None:
    pd.DataFrame(
        {
            "source": ["rajasthan_ration"] * 3 + ["bihar_land"],
            "link_tier": ["T2", "T2", "T1", "exact_name_and_relative"],
            "link_id": ["r:1", "r:2", "r:3", "b:1"],
            "roll_id": ["v1", "v2", "v3", "v4"],
            "external_id": ["c:1", "c:2", "c:3", "a:1"],
            "roll_name_raw": [
                "Poorna Devi",
                "Poorna Devi",
                "KamlaSharma",
                "Ram Rai",
            ],
            "external_name_raw": [
                "Porna Devi",
                "Porna Devi",
                "Kamla Sharma",
                "Ram Rai",
            ],
            "roll_relative_raw": ["Ram", "Ram", "Mohan", "Hari Rai"],
            "external_relative_raw": ["Ram", "Ram", "Mohan", "Hari Rai"],
            "relation_type": ["father"] * 4,
            "sex": ["f", "f", "f", None],
            "name_exact_upstream": [False, False, False, True],
            "edit_learning_eligible": [True, True, False, False],
            "omission_eligible": [False, False, False, False],
        }
    ).to_parquet(path, index=False)


def test_linked_stages(tmp_path: Path) -> None:
    links = tmp_path / "links.parquet"
    alignments = tmp_path / "alignments.parquet"
    edit_model = tmp_path / "edits.json"
    variants = tmp_path / "variants.parquet"
    resolved = tmp_path / "resolved.parquet"
    family = tmp_path / "family.parquet"
    _write_links(links)
    assert align_link_table(links, alignments) > 4
    counts = learn_edit_artifact(alignments, edit_model)
    assert counts == {"rajasthan_ration": 2}
    assert json.loads(edit_model.read_text())["sources"]["rajasthan_ration"]
    assert build_variant_table(alignments, variants) == 2
    mapping = pd.read_parquet(variants)
    assert set(mapping["variant"]) == {"poorna", "porna"}
    assert resolve_linked_surnames(links, resolved) == 4
    linked = pd.read_parquet(resolved)
    assert set(linked["sex"]) == {"female", "unknown"}
    segmentation = linked.loc[linked["roll_id"] == "v3"].iloc[0]
    assert segmentation["surname"] == "sharma"
    assert segmentation["surname_provenance"] == "ration_card_segmentation"
    assert resolve_family_surnames(links, family) == 0


def test_evaluation_report(tmp_path: Path) -> None:
    candidate = tmp_path / "candidates.parquet"
    pd.DataFrame(
        {
            "state": ["bihar", "bihar"],
            "weight": [2, 3],
            "abstained": [False, True],
            "abstention_reason": [None, "single-token-name"],
            "first_candidate": ["poorna", "kamla"],
            "last_candidate": ["devi", "kamla"],
            "first_in_relative": [False, True],
            "last_in_relative": [True, False],
        }
    ).to_parquet(candidate, index=False)
    links = tmp_path / "links.parquet"
    alignments = tmp_path / "alignments.parquet"
    variants = tmp_path / "variants.parquet"
    resolved = tmp_path / "resolved.parquet"
    family = tmp_path / "family.parquet"
    _write_links(links)
    align_link_table(links, alignments)
    build_variant_table(alignments, variants)
    resolve_linked_surnames(links, resolved)
    resolve_family_surnames(links, family)
    report = evaluate_outputs(
        [candidate],
        links,
        alignments,
        variants,
        resolved,
        family,
        state_positions={"bihar": "last"},
    )
    coverage = report.loc[
        (report["scope"] == "bihar")
        & (report["metric"] == "recorded_surname_coverage"),
        "value",
    ].iloc[0]
    assert coverage == 0.4
    selected_overlap = report.loc[
        (report["scope"] == "bihar")
        & (report["metric"] == "selected_in_relative_share"),
        "value",
    ].iloc[0]
    assert selected_overlap == 0.4
    female_t2_links = report.loc[
        (report["scope"] == "rajasthan_ration:T2:sex=female")
        & (report["metric"] == "accepted_links"),
        "value",
    ].iloc[0]
    assert female_t2_links == 2
    assert pq.ParquetFile(family).metadata.num_rows == 0


def test_family_surname_stage_requires_explicitly_eligible_source(
    tmp_path: Path,
) -> None:
    links = tmp_path / "links.parquet"
    output = tmp_path / "family.parquet"
    _write_links(links)
    frame = pd.read_parquet(links)
    frame.loc[frame["roll_id"] == "v3", "roll_name_raw"] = "Kamla"
    frame.loc[frame["roll_id"] == "v3", "omission_eligible"] = True
    frame.to_parquet(links, index=False)
    assert resolve_family_surnames(links, output) == 1
    evidence = pd.read_parquet(output).iloc[0]
    assert evidence["family_surname"] == "sharma"
