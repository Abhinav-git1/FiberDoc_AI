"""Validation report: a self-contained HTML summary of a project's documents, findings and human decisions.

`render_report` is pure (no DB access) so it is easy to test. Everything that comes from documents,
the LLM or reviewers is HTML-escaped.
"""
from collections import Counter
from datetime import datetime
from html import escape as e

SEVERITIES = ["high", "medium", "low"]
DECISION_LABEL = {
    "pending": "Pending review",
    "approved": "Approved (finding confirmed)",
    "rejected": "Rejected (false alarm)",
    "changes_requested": "Changes requested",
}

STYLE = """
body{font:14px/1.5 system-ui,Segoe UI,Arial,sans-serif;color:#1f2328;max-width:860px;margin:32px auto;padding:0 20px}
h1{margin:0 0 4px}h2{margin:32px 0 10px;border-bottom:1px solid #e3e5e8;padding-bottom:4px}h3{margin:18px 0 6px}
.muted{color:#6b7280}.note{background:#fff8e1;border:1px solid #f0d98c;padding:10px 12px;border-radius:8px;margin:16px 0}
table{border-collapse:collapse;width:100%;margin:8px 0}th,td{border:1px solid #e3e5e8;padding:6px 10px;text-align:left}th{background:#f7f7f8}
.finding{border:1px solid #e3e5e8;border-left:5px solid #999;border-radius:8px;padding:10px 14px;margin:12px 0;break-inside:avoid}
.finding.high{border-left-color:#c0392b}.finding.medium{border-left-color:#d98a00}.finding.low{border-left-color:#0b7a75}
.sev{font-size:11px;font-weight:600;text-transform:uppercase}.high .sev{color:#c0392b}.medium .sev{color:#d98a00}.low .sev{color:#0b7a75}
blockquote{margin:6px 0;padding:6px 12px;background:#f7f7f8;border-left:3px solid #ccc;white-space:pre-wrap}
.comment{margin:4px 0 0 12px}
"""


def _source_label(source: str) -> str:
    return "AI-assisted (interpreted from document text)" if source == "ai" else "Rule check (deterministic)"


def render_report(project, documents: list, findings: list, generated_at: datetime) -> str:
    """`findings` items need: document_id, title, severity, source, rule_id, rule (with .text), evidence_page,
    evidence_quote, explanation, decision, comments (author, text, created_at)."""
    by_sev = Counter(f.severity for f in findings)
    by_decision = Counter(f.decision for f in findings)
    pending = by_decision.get("pending", 0)

    out = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>Validation report - {e(project.name)}</title><style>{STYLE}</style></head><body>",
        "<h1>Validation report</h1>",
        f"<div class='muted'>{e(project.name)}{' · ' + e(project.location) if project.location else ''}"
        f" · generated {generated_at:%Y-%m-%d %H:%M} UTC</div>",
        "<div class='note'><strong>Demo report.</strong> Rules are a small, clearly labelled demo set. This report is a "
        "decision-support summary, not an engineering safety or regulatory certification. AI-assisted findings "
        "must be confirmed by a human reviewer.</div>",
        "<h2>Summary</h2>",
        f"<p><strong>{len(findings)}</strong> finding(s) across <strong>{len(documents)}</strong> document(s): "
        + ", ".join(f"{by_sev.get(s, 0)} {s}" for s in SEVERITIES) + ".</p>",
        "<table><tr><th>Decision</th><th>Count</th></tr>"
        + "".join(f"<tr><td>{e(label)}</td><td>{by_decision.get(key, 0)}</td></tr>" for key, label in DECISION_LABEL.items())
        + "</table>",
    ]
    if pending:
        out.append(f"<p class='note'>{pending} finding(s) are still <strong>pending review</strong>, so this report is incomplete.</p>")

    out.append("<h2>Documents checked</h2><table><tr><th>Document</th><th>Type</th><th>Pages</th><th>Status</th></tr>")
    for d in documents:
        status = d.status + (f" - {e(d.error)}" if d.error else "")
        out.append(f"<tr><td>{e(d.name)}</td><td>{e(d.doc_type.replace('_', ' '))}</td><td>{d.page_count}</td><td>{status}</td></tr>")
    out.append("</table><h2>Findings</h2>")

    if not findings:
        out.append("<p class='muted'>No findings recorded.</p>")
    for d in documents:
        mine = [f for f in findings if f.document_id == d.id]
        if not mine:
            continue
        out.append(f"<h3>{e(d.name)}</h3>")
        for f in sorted(mine, key=lambda x: SEVERITIES.index(x.severity) if x.severity in SEVERITIES else 9):
            if f.evidence_quote:
                evidence = f"<blockquote>{e(f.evidence_quote)}</blockquote><div class='muted'>Page {f.evidence_page}</div>"
            else:
                evidence = "<div class='muted'>No supporting text found in the document for this finding.</div>"
            comments = "".join(
                f"<div class='comment'><span class='muted'>{c.created_at:%Y-%m-%d} · {e(c.author)}:</span> {e(c.text)}</div>"
                for c in f.comments
            )
            out.append(
                f"<div class='finding {e(f.severity)}'><span class='sev'>{e(f.severity)}</span> <strong>{e(f.title)}</strong>"
                f"<div class='muted'>Rule {e(f.rule_id)} · {_source_label(f.source)}</div>"
                f"<div><em>{e(f.rule.text)}</em></div>{evidence}<p>{e(f.explanation)}</p>"
                f"<div><strong>Decision:</strong> {e(DECISION_LABEL.get(f.decision, f.decision))}</div>{comments}</div>"
            )
    out.append("</body></html>")
    return "".join(out)
