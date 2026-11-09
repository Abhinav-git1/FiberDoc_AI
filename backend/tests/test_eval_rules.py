"""Evaluation set: the deterministic rules run against documents with KNOWN expected outcomes.

Needs no database or Gemini key. The PDF case parses sample_docs/MRN-S4_construction_plan.pdf
(see sample_docs/make_sample.py for its deliberate defects). The text cases cover the
"could not verify" path (passed=None).
"""
from pathlib import Path

import pytest

from app.services.document_parser import parse_document
from app.services.validators import Chunk, run_rule_check
from app.workflow.seed_rules import RULES

DETERMINISTIC = [r for r in RULES if r["check_type"] != "semantic"]
SAMPLE = Path(__file__).resolve().parent.parent / "sample_docs" / "MRN-S4_construction_plan.pdf"

# rule id -> expected `passed` for the sample PDF (True = ok, False = defect found)
SAMPLE_EXPECTED = {"QA-014": False, "DSN-011": False, "DSN-003": False, "CON-007": False}


def _run(rule_id: str, chunks: list[Chunk]):
    rule = next(r for r in DETERMINISTIC if r["id"] == rule_id)
    return run_rule_check(rule["check_type"], rule["params"], chunks)


@pytest.fixture(scope="module")
def sample_chunks():
    doc = parse_document(SAMPLE)
    return [Chunk(c.page, c.text) for c in doc.chunks]


@pytest.mark.parametrize("rule_id,expected", SAMPLE_EXPECTED.items())
def test_sample_pdf_findings(sample_chunks, rule_id, expected):
    assert _run(rule_id, sample_chunks).passed is expected


def test_sample_pdf_defect_details(sample_chunks):
    assert _run("CON-007", sample_chunks).page == 3  # 30 in. trench note
    assert "144" in _run("DSN-003", sample_chunks).explanation and "96" in _run("DSN-003", sample_chunks).explanation


def test_compliant_document_passes_everything():
    good = [Chunk(1, "Design summary: 96-count cable. Minimum bend radius 15x diameter. OTDR results attached."),
            Chunk(2, "Cable schedule: 96-count cable. Conduit buried 42 in. deep.")]
    for r in DETERMINISTIC:
        assert _run(r["id"], good).passed is True, r["id"]


def test_consistency_with_one_side_missing_is_undeterminable():
    only_summary = [Chunk(1, "Design summary: 96-count single-mode cable.")]
    res = _run("DSN-003", only_summary)
    assert res.passed is None and "Could not locate" in res.explanation


def test_compliant_sample_pdf_passes_all_deterministic_rules():
    doc = parse_document(SAMPLE.with_name("MRN-S5_compliant_plan.pdf"))
    chunks = [Chunk(c.page, c.text) for c in doc.chunks]
    for r in DETERMINISTIC:
        assert _run(r["id"], chunks).passed is True, r["id"]
