from upnaam.normalization import normalize_latin_token, normalize_name, tokenize_name


def test_normalize_name_is_conservative() -> None:
    assert normalize_name("  Poorna\u200b   Devi। ") == "poorna devi"
    assert normalize_name("O'Neil-Singh") == "o'neil-singh"


def test_normalize_name_rejects_unsupported_values() -> None:
    assert normalize_name(None) is None
    assert normalize_name(12) is None
    assert normalize_name(" \t ") is None


def test_tokenize_name_preserves_source_offsets() -> None:
    value = "  Poorna   Devi "
    tokens = tokenize_name(value)
    assert [token.raw for token in tokens] == ["Poorna", "Devi"]
    assert [value[token.start : token.end] for token in tokens] == [
        "Poorna",
        "Devi",
    ]


def test_danda_is_a_token_boundary() -> None:
    tokens = tokenize_name("राम।शर्मा")
    assert [token.raw for token in tokens] == ["राम", "शर्मा"]


def test_zero_width_joiner_is_removed_without_splitting_word() -> None:
    tokens = tokenize_name("मिस्\u200dत्री")
    assert len(tokens) == 1
    assert tokens[0].normalized == "मिस्त्री"


def test_latin_normalization_is_not_transliteration_or_canonicalization() -> None:
    assert normalize_latin_token("Rāj") == "raj"
    assert normalize_latin_token("Jadhab") == "jadhab"
    assert normalize_latin_token("ਯਾਦਵ") is None
