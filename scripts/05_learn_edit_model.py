#!/usr/bin/env python3
"""Count source-specific character edits in eligible linked pairs."""

from pathlib import Path

from upnaam.artifacts import write_manifest
from upnaam.linked_stages import learn_edit_artifact

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Learn observed edit counts, excluding circular Bihar exact links."""
    source = ROOT / "data" / "derived" / "alignments" / "token_alignments.parquet"
    output = ROOT / "data" / "derived" / "models" / "edit_counts.json"
    counts = learn_edit_artifact(source, output)
    write_manifest(
        ROOT / "data" / "manifests" / "05_learn_edit_model.json",
        stage="05_learn_edit_model",
        inputs=[source],
        outputs=[output],
        row_counts=counts,
        parameters={"eligible": "upstream-approved non-exact Rajasthan T2 pairs"},
    )


if __name__ == "__main__":
    main()
