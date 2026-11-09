from datetime import datetime, timezone
from types import SimpleNamespace as NS

from app.services.report import render_report

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def _finding(**kw):
    base = dict(document_id="d1", title="T", severity="high", source="rule", rule_id="QA-014",
                rule=NS(text="Rule text"), evidence_page=2, evidence_quote="quoted text", explanation="why",
                decision="pending", comments=[])
    return NS(**{**base, **kw})


def test_report_counts_and_pending_warning():
    project = NS(name="P1", location="Boston")
    docs = [NS(id="d1", name="a.pdf", doc_type="construction_plan", page_count=5, status="awaiting_review", error=None)]
    fs = [_finding(), _finding(severity="low", decision="approved")]
    html = render_report(project, docs, fs, NOW)
    assert "2</strong> finding(s)" in html and "1 high, 0 medium, 1 low" in html
    assert "still <strong>pending review</strong>" in html
    assert "quoted text" in html and "Page 2" in html


def test_report_escapes_untrusted_text_and_shows_comments():
    project = NS(name="<script>x</script>", location="")
    docs = [NS(id="d1", name="a.pdf", doc_type="other", page_count=1, status="awaiting_review", error=None)]
    c = NS(author="Reviewer", text="<b>ok</b>", created_at=NOW)
    fs = [_finding(explanation="<img src=x>", decision="approved", comments=[c], evidence_quote=None)]
    html = render_report(project, docs, fs, NOW)
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
    assert "<img src=x>" not in html and "&lt;b&gt;ok&lt;/b&gt;" in html
    assert "No supporting text found" in html
