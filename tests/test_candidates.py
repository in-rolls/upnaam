import pytest

from upnaam.candidates import extract_surname_candidates


def test_final_eligible_token_is_baseline_surname() -> None:
    result = extract_surname_candidates("Poorna Devi")
    assert result.surname is not None
    assert result.surname.raw == "Devi"
    assert result.first_candidate is not None
    assert result.first_candidate.raw == "Poorna"
    assert not result.abstained


def test_prefix_honorific_is_not_candidate() -> None:
    result = extract_surname_candidates("श्री राम यादव")
    assert [token.raw for token in result.eligible_tokens] == ["राम", "यादव"]
    assert result.surname is not None
    assert result.surname.raw == "यादव"


def test_single_token_abstains() -> None:
    result = extract_surname_candidates("कमला")
    assert result.last_candidate is not None
    assert result.last_candidate.raw == "कमला"
    assert result.surname is None
    assert result.abstention_reason == "single-token-name"


def test_one_letter_initial_is_excluded() -> None:
    result = extract_surname_candidates("A Sattar")
    assert [token.normalized for token in result.eligible_tokens] == ["sattar"]
    assert result.surname is None
    assert result.abstention_reason == "single-token-name"


def test_no_eligible_token_abstains() -> None:
    result = extract_surname_candidates("A B")
    assert result.abstention_reason == "no-eligible-token"


def test_invalid_minimum_raises() -> None:
    with pytest.raises(ValueError, match="at least one"):
        extract_surname_candidates("Poorna Devi", min_letters=0)
