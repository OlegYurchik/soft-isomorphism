from factkg_h11_unknown_fallback import hybrid_verdict, is_correct, parse_verdict


def test_hybrid_replaces_only_unknown_b1_verdict() -> None:
    assert hybrid_verdict("TRUE", "FALSE") == "TRUE"
    assert hybrid_verdict("FALSE", "TRUE") == "FALSE"
    assert hybrid_verdict("UNKNOWN", "TRUE") == "TRUE"


def test_parse_verdict_fails_closed_to_unknown() -> None:
    assert parse_verdict('{"verdict":"FALSE"}') == "FALSE"
    assert parse_verdict('{"verdict":"MAYBE"}') == "UNKNOWN"
    assert parse_verdict("not json") == "UNKNOWN"


def test_is_correct_treats_unknown_as_error() -> None:
    assert is_correct("TRUE", True)
    assert is_correct("FALSE", False)
    assert not is_correct("UNKNOWN", True)
