import gzip
import json
from pathlib import Path

import pandas as pd

from upnaam.profiling import profile_configured_sources, write_profile


def test_profiles_local_sources_without_cloud_queries(tmp_path: Path) -> None:
    electoral: dict[str, str] = {}
    for state in ("bihar", "rajasthan", "maharashtra", "punjab"):
        path = tmp_path / f"{state}.csv.gz"
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            stream.write(
                "english_name,father_husband_name,n_times\nRam Rai,Hari Rai,1\n"
            )
        electoral[state] = str(path)
    accepted = tmp_path / "bihar_links.parquet"
    roll = tmp_path / "bihar_roll.parquet"
    pd.DataFrame({"id": ["1"]}).to_parquet(accepted, index=False)
    pd.DataFrame({"id": ["1"]}).to_parquet(roll, index=False)
    person_root = tmp_path / "person_links"
    roll_root = tmp_path / "roll_households" / "bucket=0"
    ration_root = tmp_path / "ration_households" / "bucket=0"
    person_root.mkdir()
    roll_root.mkdir(parents=True)
    ration_root.mkdir(parents=True)
    pd.DataFrame({"id": ["1"]}).to_parquet(
        person_root / "bucket_00.parquet", index=False
    )
    pd.DataFrame({"id": ["1"]}).to_parquet(roll_root / "data_0.parquet", index=False)
    pd.DataFrame({"id": ["1"]}).to_parquet(ration_root / "data_0.parquet", index=False)
    config = {
        "electoral_name_tables": electoral,
        "bihar_land": {
            "accepted_links": str(accepted),
            "roll_records": str(roll),
        },
        "rajasthan_ration": {
            "person_links": str(person_root),
            "roll_households": str(roll_root.parent),
            "ration_households": str(ration_root.parent),
            "age_offset_audit": str(tmp_path / "age_offset.csv"),
            "accepted_tiers": ["T1", "T2"],
        },
    }
    profile = profile_configured_sources(config)
    assert (
        profile["external_sources"]["rajasthan_ration"]["person_link_partitions"] == 1
    )
    output = tmp_path / "profile.json"
    write_profile(profile, output)
    assert json.loads(output.read_text())["electoral_name_tables"]["bihar"][
        "columns"
    ] == ["english_name", "father_husband_name", "n_times"]
