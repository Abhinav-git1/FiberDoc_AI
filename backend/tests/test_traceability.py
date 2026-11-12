"""Roadmap step 3: findings carry a status, an evidence list, the pages checked, a recommended action, a
needs-human-review flag and a retrieval trace. No database or Gemini needed."""
from datetime import datetime
from types import SimpleNamespace as NS

from app.api.findings import to_out
from app.services.report import render_report
from app.services.retrieval import ScoredRule
from app.services.validators import Chunk, check_consistency, check_required_terms
from app.workflow.graph import outcome, rule_trace


def test_outcome_maps_check_result_to_status_action_and_review_flag():
    assert outcome(True, "QA-014", "OTDR") == ("compliant", "No action needed.", False)
    status, action, review = outcome(False, "QA-014", "OTDR")
    assert status == "non_compliant" and review and "QA-014" in action
    status, action, review = outcome(None, "QA-014", "OTDR")
    assert status == "unverified" and review and "by hand" in action


def test_consistency_check_cites_both_sides():
    chunks = [Chunk(1, "Design summary: fiber count 144."), Chunk(3, "Cable schedule: count 96 fibers.")]
    res = check_consistency(chunks, r"fiber count (\d+)", r"count (\d+) fibers", "fiber count")
    assert res.passed is False
    assert [e["page"] for e in res.evidence] == [1, 3]
    assert "144" in res.evidence[0]["quote"] and "96" in res.evidence[1]["quote"]


def test_evidence_is_empty_when_nothing_found():
    res = check_required_terms([Chunk(1, "nothing here")], [r"otdr"], "OTDR results")
    assert res.passed is False and res.evidence == []


def test_rule_trace_records_rule_as_used_and_ranking():
    rule = NS(id="CON-007", version="0.2", source_name="Demo catalogue", section="Construction",
              check_type="numeric_min", text="Burial depth at least 36 in.")
    scores = ScoredRule(rule, 2, 0.81234, 0.5, 0.7 * 0.81234 + 0.15).trace()
    t = rule_trace(rule, "construction_plan", scores)
    assert t["rule"]["version"] == "0.2" and t["rule"]["text"].startswith("Burial")
    assert t["ranking"] == {"rank": 2, "score": round(0.7 * 0.81234 + 0.15, 4), "vector": 0.8123, "keyword": 0.5}


def _finding(**kw):
    base = dict(id="f1", project_id="p1", document=NS(name="plan.pdf"), document_id="d1", title="Burial depth",
                severity="high", source="rule", rule_id="CON-007", rule=NS(text="Rule text", version="0.2", source_name="Demo"),
                evidence_page=2, evidence_quote="depth 30 in", explanation="too shallow", decision="pending",
                comments=[], status=None, evidence=None, source_pages_checked=None, recommended_action=None,
                needs_human_review=None, retrieval=None)
    return NS(**{**base, **kw})


def test_api_falls_back_to_legacy_evidence_columns():
    out = to_out(_finding())
    assert out.evidence.quote == "depth 30 in" and [e.page for e in out.evidence_list] == [2]
    assert out.status is None


def test_api_returns_new_fields_camelcase():
    f = _finding(status="non_compliant", evidence=[{"page": 1, "quote": "a"}, {"page": 3, "quote": "b"}],
                 source_pages_checked=[1, 2, 3], recommended_action="Fix it.", needs_human_review=True,
                 retrieval={"ranking": {"rank": 1, "score": 0.9, "vector": 0.9, "keyword": 1.0}})
    js = to_out(f).model_dump(by_alias=True)
    assert js["evidence"] == {"page": 1, "quote": "a"} and len(js["evidenceList"]) == 2
    assert js["sourcePagesChecked"] == [1, 2, 3] and js["needsHumanReview"] is True
    assert js["recommendedAction"] == "Fix it." and js["status"] == "non_compliant"


def test_report_shows_all_evidence_status_pages_rank_and_action():
    f = _finding(status="non_compliant", evidence=[{"page": 1, "quote": "first <q>"}, {"page": 3, "quote": "second"}],
                 source_pages_checked=[1, 2, 3], recommended_action="Revise <now>.",
                 retrieval={"ranking": {"rank": 4, "score": 0.6123, "vector": 0.7, "keyword": 0.4}})
    doc = NS(id="d1", name="plan.pdf", doc_type="construction_plan", page_count=3, status="awaiting_review", error=None)
    html = render_report(NS(name="P", location=""), [doc], [f], datetime(2026, 11, 12))
    assert "first &lt;q&gt;" in html and "second" in html
    assert "Non-compliant" in html and "Pages checked: 1, 2, 3" in html
    assert "rule #4 (score 0.61)" in html and "Revise &lt;now&gt;." in html
