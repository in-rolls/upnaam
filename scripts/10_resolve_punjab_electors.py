#!/usr/bin/env python3
"""Build the row-preserving Punjab elector surname artifact."""

import argparse
from pathlib import Path

from upnaam.artifacts import write_manifest
from upnaam.punjab import (
    PUNJAB_RESOLVER_REVISION,
    PUNJAB_SOURCE_REVISION,
    PUNJAB_TRANSLITERATION_REVISION,
    build_punjab_elector_artifact,
    write_punjab_audit,
    write_punjab_summary,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROLL = ROOT / "data" / "source" / "dataverse" / "punjab_all_clean+t13n.csv.gz"
DEFAULT_TRANSLITERATIONS = (
    ROOT.parent / "indicate" / "data" / "punjab_transliteration_subset.parquet"
)
DEFAULT_OUTPUT = ROOT / "data" / "derived" / "electors" / "punjab.parquet"
DEFAULT_AUDIT = ROOT / "data" / "audit" / "punjab_elector_resolution.json"
DEFAULT_SUMMARY = ROOT / "data" / "audit" / "punjab_elector_resolution.csv"
DEFAULT_MANIFEST = ROOT / "data" / "manifests" / "10_resolve_punjab_electors.json"


def parse_args() -> argparse.Namespace:
    """Parse explicit source and output locations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roll", type=Path, default=DEFAULT_ROLL)
    parser.add_argument(
        "--transliterations", type=Path, default=DEFAULT_TRANSLITERATIONS
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--batch-size", type=int, default=100_000)
    return parser.parse_args()


def main() -> None:
    """Run the Punjab resolver and record its exact source revisions."""
    args = parse_args()
    report = build_punjab_elector_artifact(
        args.roll,
        args.transliterations,
        args.output,
        batch_size=args.batch_size,
    )
    write_punjab_audit(args.audit, report)
    write_punjab_summary(args.summary, report)
    write_manifest(
        args.manifest,
        stage="10_resolve_punjab_electors",
        inputs=[args.roll, args.transliterations],
        outputs=[args.output, args.audit, args.summary],
        row_counts={
            "roll": report.rows,
            "transliterations": report.rows,
            "output": report.rows,
        },
        parameters={
            "source_revision": PUNJAB_SOURCE_REVISION,
            "resolver_revision": PUNJAB_RESOLVER_REVISION,
            "transliteration_revision": PUNJAB_TRANSLITERATION_REVISION,
            "rule": "final_eligible_token",
            "minimum_alphabetic_characters": 2,
            "row_join": "zero_based_source_row_with_native_field_validation",
            "latin_alignment": "equal_full_name_token_count_and_same_position",
            "batch_size": args.batch_size,
        },
    )


if __name__ == "__main__":
    main()
