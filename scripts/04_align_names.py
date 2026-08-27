#!/usr/bin/env python3
"""Align names within accepted external-record links."""

from pathlib import Path

from upnaam.artifacts import write_manifest
from upnaam.linked_stages import align_link_table

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Create descriptive token alignments without declaring variants."""
    source = ROOT / "data" / "derived" / "links" / "accepted_links.parquet"
    output = ROOT / "data" / "derived" / "alignments" / "token_alignments.parquet"
    rows = align_link_table(source, output)
    write_manifest(
        ROOT / "data" / "manifests" / "04_align_names.json",
        stage="04_align_names",
        inputs=[source],
        outputs=[output],
        row_counts={"alignment_operations": rows},
        parameters={"gap_cost": 1, "substitution_cost": "normalized_levenshtein"},
    )


if __name__ == "__main__":
    main()
