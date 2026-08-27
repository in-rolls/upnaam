#!/usr/bin/env python3
"""Resolve surnames for electors in accepted external-record links."""

from pathlib import Path

from upnaam.artifacts import write_manifest
from upnaam.linked_stages import resolve_linked_surnames

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Apply written-token rules plus conservative external segmentation."""
    source = ROOT / "data" / "derived" / "links" / "accepted_links.parquet"
    output = ROOT / "data" / "derived" / "resolved" / "linked_electors.parquet"
    rows = resolve_linked_surnames(source, output)
    write_manifest(
        ROOT / "data" / "manifests" / "07_resolve_linked_surnames.json",
        stage="07_resolve_linked_surnames",
        inputs=[source],
        outputs=[output],
        row_counts={"linked_electors": rows},
        parameters={
            "baseline": "final_eligible_token",
            "segmentation_rule": "external_final_token_is_exact_roll_suffix",
            "minimum_remaining_prefix_letters": 2,
            "family_surname_assignment": False,
        },
    )


if __name__ == "__main__":
    main()
