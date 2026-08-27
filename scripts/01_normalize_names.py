#!/usr/bin/env python3
"""Normalize configured electoral name tables."""

from pathlib import Path

from upnaam.artifacts import load_source_config, write_manifest
from upnaam.tabular import normalize_electoral_name_table

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Normalize all four approved diagnostic state tables."""
    config_path = ROOT / "config" / "sources.json"
    config = load_source_config(config_path)
    outputs: list[Path] = []
    inputs: list[Path] = []
    row_counts: dict[str, int] = {}
    for state, source_value in config["electoral_name_tables"].items():
        source = Path(source_value)
        output = ROOT / "data" / "derived" / "normalized" / f"{state}.parquet"
        rows = normalize_electoral_name_table(source, output, state=state)
        inputs.append(source)
        outputs.append(output)
        row_counts[state] = rows
    write_manifest(
        ROOT / "data" / "manifests" / "01_normalize_names.json",
        stage="01_normalize_names",
        inputs=inputs,
        outputs=outputs,
        row_counts=row_counts,
        parameters={
            "unicode_form": "NFC",
            "case": "casefold",
            "transliteration": False,
            "token_boundary": "whitespace",
        },
    )


if __name__ == "__main__":
    main()
