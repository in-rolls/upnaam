"""Versioned state-position policy for recorded-surname resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

SurnamePosition = Literal["first", "last"]


@dataclass(frozen=True, slots=True)
class ResolverPolicy:
    """Immutable state-position rules for one resolver revision."""

    revision: str
    state_positions: Mapping[str, SurnamePosition]
    unsupported_state: Literal["abstain"]

    def __post_init__(self) -> None:
        """Defensively copy state rules into a read-only mapping."""
        object.__setattr__(
            self, "state_positions", MappingProxyType(dict(self.state_positions))
        )

    @property
    def supported_states(self) -> tuple[str, ...]:
        """Return supported state identifiers in sorted order."""
        return tuple(sorted(self.state_positions))

    def position_for(self, state: str) -> SurnamePosition | None:
        """Return a state's recorded-surname position, or ``None`` to abstain."""
        return self.state_positions.get(state)


def _parse_resolver_policy(payload: object) -> ResolverPolicy:
    """Validate a decoded resolver-policy object."""
    if not isinstance(payload, dict):
        raise ValueError("resolver policy must be a JSON object")
    required = {"revision", "state_positions", "unsupported_state"}
    if set(payload) != required:
        raise ValueError(f"resolver policy fields must be exactly {sorted(required)}")
    revision = payload["revision"]
    positions = payload["state_positions"]
    unsupported = payload["unsupported_state"]
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("resolver revision must be a nonempty string")
    if not isinstance(positions, dict) or not positions:
        raise ValueError("state_positions must be a nonempty object")
    validated: dict[str, SurnamePosition] = {}
    for state, position in positions.items():
        if not isinstance(state, str) or not state or state != state.lower():
            raise ValueError("state identifiers must be nonempty lowercase strings")
        if position not in {"first", "last"}:
            raise ValueError(f"invalid surname position for {state}: {position!r}")
        validated[state] = cast("SurnamePosition", position)
    if unsupported != "abstain":
        raise ValueError("unsupported_state must be 'abstain'")
    return ResolverPolicy(
        revision=revision,
        state_positions=validated,
        unsupported_state="abstain",
    )


def load_resolver_policy(path: Path) -> ResolverPolicy:
    """Load and validate a versioned resolver policy from a file.

    Args:
        path: JSON policy file.

    Returns:
        Validated immutable policy.

    """
    with path.open(encoding="utf-8") as stream:
        payload: object = json.load(stream)
    return _parse_resolver_policy(payload)


def load_default_resolver_policy() -> ResolverPolicy:
    """Load the resolver policy packaged with Upnaam.

    Returns:
        Validated immutable default policy.

    """
    resource = files("upnaam").joinpath("resolver.json")
    with resource.open(encoding="utf-8") as stream:
        payload: object = json.load(stream)
    return _parse_resolver_policy(payload)
