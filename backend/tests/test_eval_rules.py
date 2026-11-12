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
# The sample PDFs and hand-written texts below predate the v0.2 catalogue, so "passes everything" means the
# original four deterministic rules. Every rule (old and new) is covered by its own examples in test_catalogue.py.
CORE = ["QA-014", "DSN-011", "DSN-003", "CON-007"]
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
    for rid in CORE:
        assert _run(rid, good).passed is True, rid


def test_consistency_with_one_side_missing_is_undeterminable():
    only_summary = [Chunk(1, "Design summary: 96-count single-mode cable.")]
    res = _run("DSN-003", only_summary)
    assert res.passed is None and "Could not locate" in res.explanation


def test_compliant_sample_pdf_passes_all_deterministic_rules():
    doc = parse_document(SAMPLE.with_name("MRN-S5_compliant_plan.pdf"))
    chunks = [Chunk(c.page, c.text) for c in doc.chunks]
    for rid in CORE:
        assert _run(rid, chunks).passed is True, rid


# The live eval (evals/cases.py) spends Gemini quota, so check its deterministic expectations here first:
# a mistake in a case is then caught for free. Semantic rules (PRM-002) are skipped.
from evals.cases import CASES  # noqa: E402

_BY_ID = {r["id"]: r for r in DETERMINISTIC}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_live_eval_case_expectations_hold_for_deterministic_rules(case):
    chunks = [Chunk(i + 1, text) for i, text in enumerate(case.pages)]
    for rid in case.flag + case.ok:
        rule = _BY_ID.get(rid)
        if rule is None:
            continue
        assert not rule["applies_to"] or case.doc_type in rule["applies_to"], f"{rid} does not apply to {case.doc_type}"
        res = run_rule_check(rule["check_type"], rule["params"], chunks)
        if rid in case.flag:  # a finding is produced for False and for "could not verify" (None)
            assert res.passed is not True, f"{rid} should be flagged: {res.explanation}"
        else:
            assert res.passed is True, f"{rid} should be OK: {res.explanation}"
