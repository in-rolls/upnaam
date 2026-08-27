#!/usr/bin/env python3
"""Resolve recorded surnames using the approved baseline."""

import argparse
from pathlib import Path

from upnaam.artifacts import write_manifest
from upnaam.tabular import load_variant_map, resolve_recorded_surnames

ROOT = Path(__file__).resolve().parents[1]
STATES = ("bihar", "rajasthan", "maharashtra", "punjab")


def parse_args() -> argparse.Namespace:
    """Parse the state-scoped stage arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=STATES, required=True)
    return parser.parse_args()


def main() -> None:
    """Resolve one state's final eligible tokens and supported variants."""
    state = parse_args().state
    variant_path = ROOT / "data" / "derived" / "variants" / "variants.parquet"
    variants = load_variant_map(variant_path)
    source = ROOT / "data" / "derived" / "candidates" / f"{state}.parquet"
    output = ROOT / "data" / "derived" / "resolved" / f"{state}.parquet"
    rows = resolve_recorded_surnames(source, output, variants=variants)
    write_manifest(
        ROOT / "data" / "manifests" / f"07_resolve_surnames_{state}.json",
        stage="07_resolve_surnames",
        inputs=[variant_path, source],
        outputs=[output],
        row_counts={state: rows},
        parameters={
            "state": state,
            "rule": "final_eligible_token",
            "scores_calibrated": False,
            "family_surname_assignment": False,
        },
    )


if __name__ == "__main__":
    main()
