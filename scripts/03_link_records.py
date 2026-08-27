#!/usr/bin/env python3
"""Materialize accepted Bihar land and Rajasthan ration links."""

from pathlib import Path

from upnaam.artifacts import load_source_config, write_manifest
from upnaam.parquet import combine_parquet_files
from upnaam.source_links import build_bihar_land_links, build_rajasthan_ration_links

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Reuse only the existing source-specific accepted links."""
    config_path = ROOT / "config" / "sources.json"
    config = load_source_config(config_path)
    link_directory = ROOT / "data" / "derived" / "links"
    bihar_output = link_directory / "bihar_land.parquet"
    rajasthan_output = link_directory / "rajasthan_ration.parquet"
    combined_output = link_directory / "accepted_links.parquet"
    bihar = config["bihar_land"]
    rajasthan = config["rajasthan_ration"]
    bihar_rows = build_bihar_land_links(
        Path(bihar["accepted_links"]), Path(bihar["roll_records"]), bihar_output
    )
    rajasthan_rows = build_rajasthan_ration_links(
        Path(rajasthan["person_links"]),
        Path(rajasthan["roll_households"]),
        Path(rajasthan["ration_households"]),
        Path(rajasthan["age_offset_audit"]),
        rajasthan_output,
        accepted_tiers=tuple(rajasthan["accepted_tiers"]),
    )
    combined_rows = combine_parquet_files(
        [bihar_output, rajasthan_output], combined_output
    )
    write_manifest(
        ROOT / "data" / "manifests" / "03_link_records.json",
        stage="03_link_records",
        inputs=[
            Path(bihar["accepted_links"]),
            Path(bihar["roll_records"]),
            Path(rajasthan["person_links"]),
            Path(rajasthan["roll_households"]),
            Path(rajasthan["ration_households"]),
            Path(rajasthan["age_offset_audit"]),
        ],
        outputs=[bihar_output, rajasthan_output, combined_output],
        row_counts={
            "bihar_land": bihar_rows,
            "rajasthan_ration": rajasthan_rows,
            "combined": combined_rows,
        },
        parameters={
            "rajasthan_tiers": list(rajasthan["accepted_tiers"]),
            "rajasthan_relinked": False,
            "bihar_link_type": "upstream_exact_normalized_name_and_relative",
        },
    )


if __name__ == "__main__":
    main()
