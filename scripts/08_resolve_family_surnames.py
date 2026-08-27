#!/usr/bin/env python3
"""Resolve separately reported externally evidenced family surnames."""

from pathlib import Path

from upnaam.artifacts import write_manifest
from upnaam.linked_stages import resolve_family_surnames

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Emit conservative fuller-name evidence without overwriting surnames."""
    source = ROOT / "data" / "derived" / "links" / "accepted_links.parquet"
    output = ROOT / "data" / "derived" / "family" / "family_surnames.parquet"
    rows = resolve_family_surnames(source, output)
    write_manifest(
        ROOT / "data" / "manifests" / "08_resolve_family_surnames.json",
        stage="08_resolve_family_surnames",
        inputs=[source],
        outputs=[output],
        row_counts={"family_surname_candidates": rows},
        parameters={
            "external_rule": "final_eligible_token",
            "requires_external_name_longer": True,
            "requires_external_final_token_absent_from_roll": True,
            "bihar_exact_links_eligible": False,
        },
    )


if __name__ == "__main__":
    main()
