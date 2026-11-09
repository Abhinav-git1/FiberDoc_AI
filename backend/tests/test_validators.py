from app.services.validators import (
    Chunk,
    check_consistency,
    check_numeric_min,
    check_required_terms,
    quote_is_grounded,
)

DEPTH = r"(\d+(?:\.\d+)?)\s*in\."


def test_required_term_missing():
    r = check_required_terms([Chunk(1, "Splice plan with 24 points.")], [r"otdr"], "OTDR results")
    assert r.passed is False and r.quote is None


def test_required_term_found_has_page_and_quote():
    r = check_required_terms([Chunk(3, "x"), Chunk(5, "OTDR trace attached")], [r"otdr"], "OTDR")
    assert r.passed and r.page == 5 and "OTDR" in r.quote


def test_numeric_min_fails_below():
    r = check_numeric_min([Chunk(4, "Trench to approximately 30 in. along shoulder")], DEPTH, 36, "in", "burial depth")
    assert r.passed is False and r.page == 4


def test_numeric_min_passes():
    assert check_numeric_min([Chunk(1, "Depth 42 in.")], DEPTH, 36, "in", "depth").passed


def test_numeric_min_missing_value_is_not_a_pass():
    assert check_numeric_min([Chunk(1, "no depth")], DEPTH, 36, "in", "depth").passed is False


def test_consistency_mismatch():
    chunks = [Chunk(2, "Design summary: 144-count cable"), Chunk(6, "Cable schedule: 96-count cable")]
    r = check_consistency(chunks, r"design summary[^.\n]*?(\d+)-count", r"cable schedule[^.\n]*?(\d+)-count", "fiber count")
    assert r.passed is False and "144" in r.explanation and "96" in r.explanation


def test_consistency_undeterminable():
    r = check_consistency([Chunk(1, "nothing")], r"a(\d+)", r"b(\d+)", "x")
    assert r.passed is None


def test_quote_grounding_rejects_invented_text():
    chunks = [Chunk(1, "Trench to be   excavated to approximately 30 in.")]
    assert quote_is_grounded("excavated to approximately 30 in.", chunks)
    assert not quote_is_grounded("buried at 48 inches", chunks)
    assert not quote_is_grounded(None, chunks)
