#!/usr/bin/env python3
"""Cluster directly supported spelling variants."""

from pathlib import Path

from upnaam.artifacts import write_manifest
from upnaam.linked_stages import build_variant_table

ROOT = Path(__file__).resolve().parents[1]
MIN_SUPPORT = 2
MIN_SIMILARITY = 0.75


def main() -> None:
    """Build conservative complete-link clusters at declared thresholds."""
    source = ROOT / "data" / "derived" / "alignments" / "token_alignments.parquet"
    output = ROOT / "data" / "derived" / "variants" / "variants.parquet"
    rows = build_variant_table(
        source, output, min_support=MIN_SUPPORT, min_similarity=MIN_SIMILARITY
    )
    write_manifest(
        ROOT / "data" / "manifests" / "06_cluster_variants.json",
        stage="06_cluster_variants",
        inputs=[source],
        outputs=[output],
        row_counts={"variant_mappings": rows},
        parameters={
            "minimum_direct_link_support": MIN_SUPPORT,
            "minimum_normalized_similarity": MIN_SIMILARITY,
            "merge_rule": "complete_link_direct_evidence",
        },
    )


if __name__ == "__main__":
    main()
