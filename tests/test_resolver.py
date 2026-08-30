import pandas as pd
import pytest

from upnaam import resolve_electors


def test_resolve_electors_preserves_rows_and_applies_state_policy() -> None:
    records = pd.DataFrame(
        {
            "elector_id": ["roll:1", "roll:2", "roll:3", "roll:4"],
            "state": ["bihar", "maharashtra", "bihar", "goa"],
            "name": ["Poorna Devi", "Patil Ashwini", "Kamla", "Ana Costa"],
            "unused_relative": ["Ram Sharma", "Patil Ashok", None, None],
        }
    )
    result = resolve_electors(records)
    assert list(result["elector_id"]) == list(records["elector_id"])
    assert result.loc[0, "surname_raw"] == "Devi"
    assert result.loc[0, "surname_source_normalized"] == "devi"
    assert result.loc[0, "surname_latin_normalized"] == "devi"
    assert result.loc[0, "surname_canonical"] == "devi"
    assert result.loc[0, "canonicalization_status"] == "identity_unmapped"
    assert result.loc[0, "surname_position"] == "last"
    assert result.loc[0, "surname_provenance"] == "written_final_token"
    assert result.loc[1, "surname_canonical"] == "patil"
    assert result.loc[1, "surname_position"] == "first"
    assert result.loc[1, "surname_provenance"] == "written_first_token"
    assert result.loc[2, "abstention_reason"] == "single-token-name"
    assert result.loc[2, "canonicalization_status"] == "not_applicable"
    assert result.loc[3, "abstention_reason"] == "unsupported-state"
    assert result.loc[3, "abstained"]
    assert set(result["normalization_revision"]) == {"normalization-v1"}
    assert set(result["resolver_revision"]) == {"resolver-v1"}


def test_resolve_electors_preserves_raw_devanagari_token() -> None:
    records = pd.DataFrame(
        {"elector_id": ["roll:1"], "state": ["bihar"], "name": ["श्री राम यादव"]}
    )
    result = resolve_electors(records)
    assert result.loc[0, "surname_raw"] == "यादव"
    assert result.loc[0, "surname_source_normalized"] == "यादव"
    assert pd.isna(result.loc[0, "surname_canonical"])
    assert result.loc[0, "canonicalization_status"] == "normalization_unavailable"


@pytest.mark.parametrize(
    ("records", "message"),
    [
        (pd.DataFrame({"elector_id": ["x"], "state": ["bihar"]}), "missing"),
        (
            pd.DataFrame(
                {
                    "elector_id": ["x", "x"],
                    "state": ["bihar", "bihar"],
                    "name": ["A B", "C D"],
                }
            ),
            "unique",
        ),
        (
            pd.DataFrame({"elector_id": ["x"], "state": ["Bihar"], "name": ["A B"]}),
            "lowercase",
        ),
    ],
)
def test_resolve_electors_rejects_invalid_input(
    records: pd.DataFrame, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_electors(records)
