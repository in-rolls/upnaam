"""Public one-row-per-elector recorded-surname interface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from upnaam.candidates import extract_surname_candidates
from upnaam.normalization import NORMALIZATION_REVISION
from upnaam.policy import ResolverPolicy, load_default_resolver_policy

if TYPE_CHECKING:
    from upnaam.normalization import NameToken

ELECTOR_INPUT_COLUMNS = ("elector_id", "state", "name")
ELECTOR_OUTPUT_COLUMNS = (
    "elector_id",
    "state",
    "name_raw",
    "surname",
    "surname_raw",
    "surname_position",
    "surname_provenance",
    "abstained",
    "abstention_reason",
    "normalization_revision",
    "resolver_revision",
)


def _validate_elector_records(records: pd.DataFrame) -> None:
    """Validate identifiers and state labels before surname resolution."""
    missing = set(ELECTOR_INPUT_COLUMNS).difference(records.columns)
    if missing:
        raise ValueError(f"elector records are missing columns: {sorted(missing)}")
    identifiers = cast("pd.Series", records["elector_id"])
    valid_identifier = identifiers.map(
        lambda value: isinstance(value, str) and bool(value.strip())
    )
    if not bool(valid_identifier.all()):
        raise ValueError("elector_id must contain nonempty strings")
    duplicate_mask = cast("pd.Series", identifiers.duplicated(keep=False))
    duplicates = cast("pd.Series", identifiers.loc[duplicate_mask])
    if not duplicates.empty:
        examples = sorted(set(duplicates.astype(str)))[:3]
        raise ValueError(f"elector_id must be unique; duplicates include {examples}")
    states = cast("pd.Series", records["state"])
    valid_state = states.map(
        lambda value: (
            isinstance(value, str) and bool(value) and value == value.strip().casefold()
        )
    )
    if not bool(valid_state.all()):
        raise ValueError("state must contain lowercase, stripped, nonempty strings")


def resolve_electors(
    records: pd.DataFrame, *, policy: ResolverPolicy | None = None
) -> pd.DataFrame:
    """Resolve a recorded surname for each elector row or explicitly abstain.

    Args:
        records: One row per elector with unique source-qualified ``elector_id``,
            lowercase ``state``, and raw ``name``. Additional columns are
            allowed but are not interpreted by ``resolver-v1``.
        policy: Versioned state-position policy. The packaged policy is used
            when omitted.

    Returns:
        One output row per input row in the same order. Surnames are
        normalized tokens selected from the elector's own raw name. Scores,
        family surnames, household assignments, and token-type labels are not
        produced by this interface.

    """
    _validate_elector_records(records)
    effective_policy = policy or load_default_resolver_policy()
    output: list[dict[str, object]] = []
    for elector_id, state, name in records.loc[
        :, list(ELECTOR_INPUT_COLUMNS)
    ].itertuples(index=False, name=None):
        candidates = extract_surname_candidates(name)
        position = effective_policy.position_for(state)
        selected: NameToken | None = None
        if position is None:
            reason = "unsupported-state"
        elif candidates.abstained:
            reason = candidates.abstention_reason
        else:
            selected = (
                candidates.first_candidate
                if position == "first"
                else candidates.last_candidate
            )
            reason = None
        provenance_position = "final" if position == "last" else position
        output.append(
            {
                "elector_id": elector_id,
                "state": state,
                "name_raw": name if isinstance(name, str) else None,
                "surname": selected.normalized if selected is not None else None,
                "surname_raw": selected.raw if selected is not None else None,
                "surname_position": position if selected is not None else None,
                "surname_provenance": (
                    f"written_{provenance_position}_token"
                    if selected is not None
                    else None
                ),
                "abstained": selected is None,
                "abstention_reason": reason,
                "normalization_revision": NORMALIZATION_REVISION,
                "resolver_revision": effective_policy.revision,
            }
        )
    return pd.DataFrame(output, columns=cast("Any", ELECTOR_OUTPUT_COLUMNS))
