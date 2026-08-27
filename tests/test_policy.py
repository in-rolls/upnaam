import json
from pathlib import Path

import pytest

from upnaam.policy import load_resolver_policy


def _write_policy(path: Path, **overrides: object) -> None:
    payload: dict[str, object] = {
        "revision": "resolver-v1",
        "state_positions": {"bihar": "last", "maharashtra": "first"},
        "unsupported_state": "abstain",
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_resolver_policy(tmp_path: Path) -> None:
    path = tmp_path / "resolver.json"
    _write_policy(path)
    policy = load_resolver_policy(path)
    assert policy.revision == "resolver-v1"
    assert policy.supported_states == ("bihar", "maharashtra")
    assert policy.position_for("bihar") == "last"
    assert policy.position_for("maharashtra") == "first"
    assert policy.position_for("goa") is None
    with pytest.raises(TypeError):
        policy.state_positions["goa"] = "first"  # type: ignore[index]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"revision": ""}, "nonempty"),
        ({"state_positions": {}}, "nonempty"),
        ({"state_positions": {"Bihar": "last"}}, "lowercase"),
        ({"state_positions": {"bihar": "middle"}}, "invalid surname position"),
        ({"unsupported_state": "error"}, "must be 'abstain'"),
        ({"extra": True}, "fields must be exactly"),
    ],
)
def test_reject_invalid_resolver_policy(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    path = tmp_path / "resolver.json"
    _write_policy(path, **overrides)
    with pytest.raises(ValueError, match=message):
        load_resolver_policy(path)
