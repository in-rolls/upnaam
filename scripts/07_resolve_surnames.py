#!/usr/bin/env python3
"""Resolve recorded surnames using the approved state-position policy."""

import argparse
from pathlib import Path

from upnaam.artifacts import write_manifest
from upnaam.policy import ResolverPolicy, load_resolver_policy
from upnaam.tabular import load_variant_map, resolve_recorded_surnames

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "resolver.json"


def parse_args(policy: ResolverPolicy) -> argparse.Namespace:
    """Parse the state-scoped stage arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=policy.supported_states, required=True)
    return parser.parse_args()


def main() -> None:
    """Resolve one state's configured eligible token and supported variants."""
    policy = load_resolver_policy(POLICY_PATH)
    state = parse_args(policy).state
    position = policy.position_for(state)
    if position is None:
        raise ValueError(f"command-line state is unsupported: {state}")
    variant_path = ROOT / "data" / "derived" / "variants" / "variants.parquet"
    variants = load_variant_map(variant_path)
    source = ROOT / "data" / "derived" / "candidates" / f"{state}.parquet"
    output = ROOT / "data" / "derived" / "resolved" / f"{state}.parquet"
    rows = resolve_recorded_surnames(
        source, output, state=state, policy=policy, variants=variants
    )
    write_manifest(
        ROOT / "data" / "manifests" / f"07_resolve_surnames_{state}.json",
        stage="07_resolve_surnames",
        inputs=[POLICY_PATH, variant_path, source],
        outputs=[output],
        row_counts={state: rows},
        parameters={
            "state": state,
            "resolver_revision": policy.revision,
            "rule": f"{position}_eligible_token",
            "scores_calibrated": False,
            "family_surname_assignment": False,
        },
    )


if __name__ == "__main__":
    main()
