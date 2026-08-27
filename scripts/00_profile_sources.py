#!/usr/bin/env python3
"""Profile configured local source artifacts."""

from pathlib import Path

from upnaam.artifacts import load_source_config, write_manifest
from upnaam.profiling import profile_configured_sources, write_profile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Run source profiling."""
    config_path = ROOT / "config" / "sources.json"
    output = ROOT / "data" / "audit" / "source_profile.json"
    manifest = ROOT / "data" / "manifests" / "00_profile_sources.json"
    config = load_source_config(config_path)
    profile = profile_configured_sources(config)
    write_profile(profile, output)
    write_manifest(
        manifest,
        stage="00_profile_sources",
        inputs=[config_path],
        outputs=[output],
        row_counts={},
        parameters={"cloud_queries": False},
    )


if __name__ == "__main__":
    main()
