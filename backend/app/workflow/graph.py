"""LangGraph workflow:

  classify -> retrieve_rules -> validate_evidence -> risk_assessment -> human_review

Deterministic wherever possible. The LLM only (a) classifies the document when keywords
are inconclusive and (b) interprets unstructured evidence for `semantic` rules. It never
approves anything: `human_review` persists findings as `pending` and the graph ends there;
a human decision arrives later via POST /api/findings/{id}/review.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document, Finding, Rule
from app.schemas import DocClassification
from app.services import audit
from app.services.llm import get_llm
from app.services.retrieval import retrieve_rules, top_chunks_for_rule
from app.services.semantic import evaluate_semantic_rule
from app.services.validators import Chunk as VChunk
from app.services.validators import run_rule_check

DOC_TYPE_HINTS = {
    "construction_plan": ["construction plan", "scope of work", "trenching", "splice plan"],
    "design_summary": ["design summary", "design basis", "cable schedule"],
    "as_built": ["as-built", "as built", "record drawing"],
    "permit": ["permit no", "permit number", "right-of-way permit"],
    "test_report": ["otdr", "test report", "insertion loss"],
}
SEVERITY_ORDER = ["low", "medium", "high"]


class State(TypedDict, total=False):
    document_id: str
    doc_type: str
    rule_ids: list[str]
    raw_findings: list[dict]  # {rule_id, source, passed, explanation, page, quote}
    findings: list[dict]  # after risk assessment


def build_graph(db: Session):
    def _chunks(document_id: str) -> list[Chunk]:
        return list(db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.page)))

    def classify(state: State) -> State:
        chunks = _chunks(state["document_id"])
        text = " ".join(c.text for c in chunks).lower()
        scores = {t: sum(text.count(h) for h in hints) for t, hints in DOC_TYPE_HINTS.items()}
        best, hits = max(scores.items(), key=lambda kv: kv[1])
        if hits >= 2:
            doc_type = best  # deterministic path
        else:
            try:
                doc_type = get_llm().generate_structured(
                    "Classify this document into one type. Text excerpt:\n" + text[:4000], DocClassification
                ).doc_type
            except Exception:
                doc_type = "other"
        doc = db.get(Document, state["document_id"])
        doc.doc_type, doc.status = doc_type, "processing"
        db.commit()
        return {"doc_type": doc_type}

    def retrieve(state: State) -> State:
        chunks = _chunks(state["document_id"])
        text = " ".join(c.text for c in chunks)
        # Document-level embedding = mean of chunk embeddings (if present).
        embs = [c.embedding for c in chunks if c.embedding is not None]
        doc_emb = [sum(col) / len(embs) for col in zip(*embs)] if embs else None
        rules = retrieve_rules(db, state["doc_type"], text, doc_emb)
        return {"rule_ids": [r.id for r in rules]}

    def validate(state: State) -> State:
        doc_id = state["document_id"]
        vchunks = [VChunk(c.page, c.text) for c in _chunks(doc_id)]
        out: list[dict] = []
        for rid in state["rule_ids"]:
            rule = db.get(Rule, rid)
            res = run_rule_check(rule.check_type, rule.params or {}, vchunks)
            if res is not None:  # deterministic
                if res.passed is not False:
                    if res.passed:
                        out.append(dict(rule_id=rid, source="rule", passed=True, explanation=res.explanation, page=res.page, quote=res.quote))
                    else:  # undeterminable: surface it for a human instead of staying silent
                        out.append(dict(rule_id=rid, source="rule", passed=None, page=res.page, quote=res.quote,
                                        explanation=f"Could not verify automatically: {res.explanation} Manual review needed."))
                    continue
                out.append(dict(rule_id=rid, source="rule", passed=False, explanation=res.explanation, page=res.page, quote=res.quote))
                continue
            # semantic rule -> LLM over retrieved evidence, then grounding check
            ev_chunks = top_chunks_for_rule(db, doc_id, rule)
            if not ev_chunks:
                out.append(dict(rule_id=rid, source="rule", passed=False, page=None, quote=None,
                                explanation="No text relevant to this requirement was found in the document."))
                continue
            result = evaluate_semantic_rule(rid, rule.text, [VChunk(c.page, c.text) for c in ev_chunks])
            if result is not None:
                out.append(dict(rule_id=rid, **result))
        return {"raw_findings": out}

    def assess_risk(state: State) -> State:
        findings = []
        for f in state["raw_findings"]:
            rule = db.get(Rule, f["rule_id"])
            sev = rule.severity
            if f["passed"] is True:
                sev = "low"  # informational: requirement met
            elif f["source"] == "ai" and f["quote"] is None and f["passed"] is None:
                sev = SEVERITY_ORDER[max(0, SEVERITY_ORDER.index(sev) - 1)]  # unverified AI: never escalate
            title = rule.title if f["passed"] is not True else f"{rule.title} – requirement met"
            findings.append({**f, "severity": sev, "title": title})
        return {"findings": findings}

    def human_review(state: State) -> State:
        doc = db.get(Document, state["document_id"])
        for f in state["findings"]:
            db.add(Finding(
                project_id=doc.project_id, document_id=doc.id, rule_id=f["rule_id"], title=f["title"],
                severity=f["severity"], source=f["source"], evidence_page=f["page"], evidence_quote=f["quote"],
                explanation=f["explanation"], decision="pending",
            ))
        doc.status = "awaiting_review"  # pause: only a human can move findings out of 'pending'
        db.commit()
        audit.record(db, "system", "workflow_completed", "document", doc.id, findings=len(state["findings"]))
        return {}

    g = StateGraph(State)
    for name, fn in [("classify", classify), ("retrieve_rules", retrieve), ("validate_evidence", validate),
                     ("risk_assessment", assess_risk), ("human_review", human_review)]:
        g.add_node(name, fn)
    g.add_edge(START, "classify")
    g.add_edge("classify", "retrieve_rules")
    g.add_edge("retrieve_rules", "validate_evidence")
    g.add_edge("validate_evidence", "risk_assessment")
    g.add_edge("risk_assessment", "human_review")
    g.add_edge("human_review", END)
    return g.compile()


def run_workflow(db: Session, document_id: str) -> None:
    try:
        build_graph(db).invoke({"document_id": document_id})
    except Exception as e:
        db.rollback()
        doc = db.get(Document, document_id)
        doc.status, doc.error = "error", str(e)[:500]
        db.commit()
        raise
