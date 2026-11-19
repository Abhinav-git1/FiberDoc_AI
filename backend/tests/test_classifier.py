"""Document type classification (app/services/classifier.py): title-weighted keywords, an embedding tie-breaker,
Gemini as the last resort, and a confidence with a reason every time."""
from pathlib import Path

import pytest

from app.services import classifier
from app.services.document_parser import parse_document

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "demo_small_construction_plan.pdf"
TITLE = "Project notes\nRev 1\nPrepared by X\nDate\n"  # a title zone with no hints, so what follows is body text


def _pages(path: Path) -> list[str]:
    pages: dict[int, list[str]] = {}
    for c in parse_document(path).chunks:  # parser order = reading order
        pages.setdefault(c.page, []).append(c.text)
    return ["\n".join(pages[p]) for p in sorted(pages)]


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample PDF not present")
def test_sample_construction_plan_is_not_a_design_summary():
    """The regression: "Construction Plan" in the title vs "Design summary" / "Cable schedule" headings (1 to 3
    with equal weights, so every construction-only rule was skipped)."""
    c = classifier.classify(_pages(SAMPLE))
    assert c.doc_type == "construction_plan" and c.method == "keyword"
    assert c.scores["construction_plan"]["title_hits"] == 1 and c.scores["design_summary"]["body_hits"] == 3
    assert 0.5 < c.confidence < 0.95
    assert "title" in c.reason


def test_title_zone_is_the_first_non_empty_lines_of_page_one():
    title, rest = classifier.split_title("\n\nA\n\nB\nC\nD\nE\nF")
    assert title.split() == ["A", "B", "C", "D"] and rest.split() == ["E", "F"]
    s = classifier.keyword_scores(["Header\nTest Report\n\nx\ny\nOTDR trace", "insertion loss 0.3 dB"])
    assert s["test_report"] == {"title_hits": 1, "body_hits": 2, "score": 7}


def test_clear_keyword_lead_needs_no_model_calls():
    def boom(*_):
        raise AssertionError("no model call expected")

    c = classifier.classify(["As-Built Record\n", "record drawing, as-built"], [1.0, 0.0], boom, boom)
    assert c.doc_type == "as_built" and c.method == "keyword" and c.confidence == 0.95  # capped: never certain


def test_close_call_is_settled_by_the_embedding():
    pages = [TITLE + "The design summary and the scope of work are attached. Trenching is listed."]
    # keywords: construction 2 (scope of work, trenching) vs design 1: a lead of one hit is not decisive
    order = []

    def embed(texts):
        order.extend(texts)
        return [[0.0, 1.0] if "design summary" in t.lower() else [1.0, 0.0] for t in texts]

    c = classifier.classify(pages, doc_embedding=[0.1, 0.9], embed_types=embed)
    assert c.method == "keyword+embedding" and c.doc_type == "design_summary"
    assert 0.5 <= c.confidence <= 0.75
    assert len(order) == 2  # only the close types are compared
    assert "similarity" in c.scores["design_summary"]


def test_close_call_without_embeddings_keeps_the_leader_and_says_so():
    pages = [TITLE + "scope of work, trenching, design summary"]
    c = classifier.classify(pages, doc_embedding=None, embed_types=None)
    assert c.doc_type == "construction_plan" and c.method == "keyword"
    assert "Manual check advised" in c.reason and c.confidence == round(2 / 3, 2)


def test_failing_tie_breaker_falls_back_to_the_leader():
    def embed(_):
        raise RuntimeError("503")

    c = classifier.classify([TITLE + "scope of work, trenching, design summary"], [1.0], embed)
    assert c.doc_type == "construction_plan" and c.method == "keyword"


def test_no_keywords_asks_gemini_and_survives_its_failure():
    c = classifier.classify(["Meeting minutes"], ask_llm=lambda excerpt: "permit")
    assert (c.doc_type, c.method, c.confidence) == ("permit", "llm", 0.6)

    def down(_):
        raise RuntimeError("503")

    c = classifier.classify(["Meeting minutes"], ask_llm=down)
    assert (c.doc_type, c.method, c.confidence) == ("other", "none", 0.0)


def test_design_summary_mentioning_construction_stays_a_design_summary(tmp_path):
    """The opposite trap: a design summary whose text mentions the construction plan, scope of work and trenching
    (sample_docs/make_design_summary.py). Title weighting must not tip it over."""
    import subprocess
    import sys

    out = tmp_path / "design.pdf"
    script = Path(__file__).resolve().parents[1] / "sample_docs" / "make_design_summary.py"
    subprocess.run([sys.executable, str(script), str(out)], check=True, capture_output=True)
    c = classifier.classify(_pages(out))
    assert c.doc_type == "design_summary" and c.method == "keyword"
    assert c.scores["construction_plan"]["body_hits"] == 3
