"""LIVE evaluation of the semantic (Gemini) rules against the sample PDFs.

Calls the real Gemini API, so it is skipped unless you opt in:
    $env:RUN_LIVE_EVAL = "1"; .venv\Scripts\python.exe -m pytest tests/test_eval_semantic.py -q
Runs are traced to LangSmith if tracing is on. Each case feeds the WHOLE (small) document as evidence, so it
tests the prompt + grounding logic, not retrieval.
"""
import os
from pathlib import Path

import pytest

from app.services.document_parser import parse_document
from app.services.semantic import evaluate_semantic_rule
from app.services.validators import Chunk
from app.workflow.seed_rules import RULES

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_EVAL") != "1", reason="live Gemini eval; set RUN_LIVE_EVAL=1")

DOCS = Path(__file__).resolve().parent.parent / "sample_docs"
RULE = {r["id"]: r for r in RULES}

# (file, rule, expect_finding)  -- expect_finding=True means the rule is violated
CASES = [
    ("MRN-S4_construction_plan.pdf", "PRM-002", True),     # "city permit (copy on file)", no number
    ("MRN-S5_compliant_plan.pdf", "PRM-002", False),       # "City Permit No. CP-2291"
    ("MRN-S6_asbuilt_bad_tags.pdf", "LBL-001", True),      # 'blue cable', 'CBL-7'
    ("MRN-S7_asbuilt_good_tags.pdf", "LBL-001", False),    # HH-03/RouteA/96F ...
]


@pytest.mark.parametrize("filename,rule_id,expect_finding", CASES)
def test_semantic_rule(filename, rule_id, expect_finding):
    chunks = [Chunk(c.page, c.text) for c in parse_document(DOCS / filename).chunks]
    result = evaluate_semantic_rule(rule_id, RULE[rule_id]["text"], chunks)
    if result and "interpretation failed" in result["explanation"]:
        pytest.skip(f"Gemini unavailable (quota / outage): {result['explanation']}")
    if expect_finding:
        assert result is not None and result["passed"] is False, result
        assert result["quote"], "a violation must cite a verbatim quote"
    else:
        assert result is None, result
