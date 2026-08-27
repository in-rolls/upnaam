#!/usr/bin/env python3
"""Evaluate baseline rules and artifact coverage."""

from pathlib import Path

from upnaam.artifacts import write_manifest
from upnaam.linked_stages import evaluate_outputs
from upnaam.policy import load_resolver_policy

ROOT = Path(__file__).resolve().parents[1]
STATES = ("bihar", "rajasthan", "maharashtra", "punjab")


def main() -> None:
    """Write long-form weighted state and accepted-link diagnostics."""
    policy_path = ROOT / "config" / "resolver.json"
    policy = load_resolver_policy(policy_path)
    candidates = [
        ROOT / "data" / "derived" / "candidates" / f"{state}.parquet"
        for state in STATES
    ]
    links = ROOT / "data" / "derived" / "links" / "accepted_links.parquet"
    alignments = ROOT / "data" / "derived" / "alignments" / "token_alignments.parquet"
    variants = ROOT / "data" / "derived" / "variants" / "variants.parquet"
    linked_resolved = ROOT / "data" / "derived" / "resolved" / "linked_electors.parquet"
    family = ROOT / "data" / "derived" / "family" / "family_surnames.parquet"
    output = ROOT / "data" / "audit" / "evaluation.csv"
    report = evaluate_outputs(
        candidates,
        links,
        alignments,
        variants,
        linked_resolved,
        family,
        state_positions=policy.state_positions,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output, index=False)
    write_manifest(
        ROOT / "data" / "manifests" / "09_evaluate.json",
        stage="09_evaluate",
        inputs=[
            policy_path,
            *candidates,
            links,
            alignments,
            variants,
            linked_resolved,
            family,
        ],
        outputs=[output],
        row_counts={"metrics": len(report)},
        parameters={
            "resolver_revision": policy.revision,
            "state_metrics_weighted_by": "n_times",
            "relative_overlap_comparison": "exact_normalized_token",
            "linked_record_strata": ["source", "tier", "sex"],
        },
    )


if __name__ == "__main__":
    main()
