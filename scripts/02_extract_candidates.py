#!/usr/bin/env python3
"""Extract positional surname candidates."""

import argparse
from pathlib import Path

from upnaam.artifacts import write_manifest
from upnaam.tabular import extract_candidate_table

ROOT = Path(__file__).resolve().parents[1]
STATES = ("bihar", "rajasthan", "maharashtra", "punjab")


def parse_args() -> argparse.Namespace:
    """Parse the state-scoped stage arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=STATES, required=True)
    return parser.parse_args()


def main() -> None:
    """Apply the approved simple candidate rules to one state artifact."""
    state = parse_args().state
    source = ROOT / "data" / "derived" / "normalized" / f"{state}.parquet"
    output = ROOT / "data" / "derived" / "candidates" / f"{state}.parquet"
    rows = extract_candidate_table(source, output)
    write_manifest(
        ROOT / "data" / "manifests" / f"02_extract_candidates_{state}.json",
        stage="02_extract_candidates",
        inputs=[source],
        outputs=[output],
        row_counts={state: rows},
        parameters={
            "state": state,
            "minimum_alphabetic_characters": 2,
            "single_eligible_token": "abstain",
            "baseline": "final_eligible_token",
            "honorific_scope": "approved_prefixes_in_prefix_position_only",
        },
    )


if __name__ == "__main__":
    main()
