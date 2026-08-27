from pathlib import Path

import pandas as pd

from upnaam.source_links import build_bihar_land_links, build_rajasthan_ration_links


def test_bihar_adapter_marks_circular_links_ineligible(tmp_path: Path) -> None:
    accepted = tmp_path / "accepted.parquet"
    roll = tmp_path / "roll.parquet"
    output = tmp_path / "links.parquet"
    pd.DataFrame(
        {
            "account_no": ["a1"],
            "name": ["राम राय"],
            "fatherraw": ["हरि राय"],
            "nm": ["राम राय"],
            "rname": ["हरि राय"],
            "vid": ["v1"],
            "relationship": ["father"],
            "sex_obs": ["male"],
        }
    ).to_parquet(accepted, index=False)
    pd.DataFrame(
        {
            "id": ["v1"],
            "elector_name": ["राम राय"],
            "father_or_husband_name": ["हरि राय"],
        }
    ).to_parquet(roll, index=False)
    assert build_bihar_land_links(accepted, roll, output) == 1
    result = pd.read_parquet(output).iloc[0]
    assert not result["edit_learning_eligible"]
    assert not result["omission_eligible"]


def test_rajasthan_adapter_keeps_only_t1_t2(tmp_path: Path) -> None:
    person_links = tmp_path / "persons"
    roll_root = tmp_path / "rolls"
    ration_root = tmp_path / "ration"
    person_links.mkdir()
    (roll_root / "bucket=0").mkdir(parents=True)
    (ration_root / "bucket=0").mkdir(parents=True)
    output = tmp_path / "links.parquet"
    age_audit = tmp_path / "age_offset.csv"
    pd.DataFrame({"offset_median": [3]}).to_csv(age_audit, index=False)
    pd.DataFrame(
        {
            "card_no": ["c1", "c2"],
            "member_no": [1, 1],
            "elector_uid": ["v1", "v2"],
            "hh_id": ["h1", "h2"],
            "tier": ["T2", "T3"],
            "name_exact": [False, False],
            "father_skel_eq": [True, True],
            "age_resid": [0.0, 0.0],
            "relationship_dev": ["स्वयं", "स्वयं"],
            "sex_std": ["f", "m"],
        }
    ).to_parquet(person_links / "bucket_00.parquet", index=False)
    pd.DataFrame(
        {
            "elector_uid": ["v1", "v2"],
            "name_dev": ["पूर्णा देवी", "मोहन लाल"],
            "rel_name_dev": ["राम", "हरि"],
            "relation_type": ["father", "father"],
            "sex_std": ["f", "m"],
            "age_2018": [30, 40],
            "name_skel": ["परणदव", "महनलल"],
            "rel_skel": ["रम", "हर"],
            "hh_id": ["h1", "h2"],
        }
    ).to_parquet(roll_root / "bucket=0" / "data_0.parquet", index=False)
    pd.DataFrame(
        {
            "card_no": ["c1", "c2"],
            "member_no": [1, 1],
            "name_dev": ["पुर्णा देवी", "मोहन लाल"],
            "member_father_dev": ["राम", "हरि"],
            "age_2021": [33, 43],
            "name_skel": ["परणदव", "महनलल"],
            "father_skel": ["रम", "हर"],
        }
    ).to_parquet(ration_root / "bucket=0" / "data_0.parquet", index=False)
    assert (
        build_rajasthan_ration_links(
            person_links, roll_root, ration_root, age_audit, output
        )
        == 1
    )
    result = pd.read_parquet(output).iloc[0]
    assert result["link_tier"] == "T2"
    assert result["edit_learning_eligible"]
