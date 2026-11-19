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
from app.services import audit, classifier
from app.services.llm import get_llm
from app.services.retrieval import evidence_chunks_for_rule, rank_rules
from app.services import timing
from app.services.semantic import evaluate_semantic_rule
from app.services.validators import Chunk as VChunk
from app.services.validators import run_rule_check

SEVERITY_ORDER = ["low", "medium", "high"]
EXCERPT_CHARS = 300  # how much of each evidence chunk the retrieval trace keeps


class State(TypedDict, total=False):
    document_id: str
    doc_type: str
    rule_ids: list[str]
    rule_scores: dict[str, dict]  # rule id -> {rank, score, vector, keyword}
    # {rule_id, source, passed, missing, explanation, page, quote, evidence, pages_checked, evidence_chunks, evidence_method}
    raw_findings: list[dict]
    findings: list[dict]  # after risk assessment


def outcome(passed: bool | None, missing: bool, rule_id: str, title: str) -> tuple[str, str, bool]:
    """(status, recommended_action, needs_human_review) for a check result, using the blueprint's four statuses:

      passed            the requirement is met, with evidence
      failed            evidence was found and it breaks the requirement (e.g. 30 in. depth vs a 36 in. minimum)
      missing_evidence  the check looked and found nothing to judge (no OTDR results, no depth stated)
      needs_review      something was found but the automation could not decide (unclear, unverified AI answer)

    Deterministic: no LLM wording. needs_human_review means the automation could not settle the rule by itself.
    Every finding still waits for a human decision either way."""
    if passed is True:
        return "passed", "No action needed.", False
    if missing:
        return ("missing_evidence",
                f"Add the evidence for {rule_id} ({title}) to the document, or mark the rule not applicable.", True)
    if passed is False:
        return "failed", f"Revise the document so it meets {rule_id} ({title}), or record an approved exception.", True
    return "needs_review", f"Check the document against {rule_id} ({title}) by hand; the automatic check could not decide.", True


def rule_trace(rule: Rule, doc_type: str, scores: dict | None) -> dict:
    """What a reviewer needs to see why this rule was applied: the rule exactly as used, and how it ranked."""
    return {
        "rule": {"id": rule.id, "version": rule.version, "source_name": rule.source_name, "section": rule.section,
                 "check_type": rule.check_type, "text": rule.text},
        "doc_type": doc_type,
        "ranking": scores,
    }


def _mean_embedding(chunks: list[Chunk]) -> list[float] | None:
    """Document-level embedding: the mean of its chunk embeddings (None if none were embedded)."""
    embs = [c.embedding for c in chunks if c.embedding is not None]
    return [sum(col) / len(embs) for col in zip(*embs)] if embs else None


_type_vectors: dict[str, list[float]] = {}  # description -> embedding; the descriptions are fixed, so embed once


def _embed_type_descriptions(texts: list[str]) -> list[list[float]]:
    missing = [t for t in texts if t not in _type_vectors]
    if missing:
        _type_vectors.update(zip(missing, get_llm().embed(missing)))
    return [_type_vectors[t] for t in texts]


def _timed(name: str, fn):
    """Wrap a workflow node so its duration is recorded in the timing breakdown."""
    def node(state: State) -> State:
        with timing.step(name):
            return fn(state)
    return node


def build_graph(db: Session):
    def _chunks(document_id: str) -> list[Chunk]:
        return list(db.scalars(select(Chunk).where(Chunk.document_id == document_id)
                               .order_by(Chunk.page, Chunk.seq.asc().nulls_last())))

    def classify(state: State) -> State:
        """Document type from weighted keywords, an embedding tie-breaker and Gemini (app/services/classifier.py)."""
        chunks = _chunks(state["document_id"])
        pages: dict[int, list[str]] = {}
        for ch in chunks:
            pages.setdefault(ch.page, []).append(ch.text)
        page_texts = ["\n".join(pages[p]) for p in sorted(pages)]
        result = classifier.classify(
            page_texts, _mean_embedding(chunks), embed_types=_embed_type_descriptions,
            ask_llm=lambda excerpt: get_llm().generate_structured(
                "Classify this document into one type. Text excerpt:\n" + excerpt, DocClassification).doc_type)
        doc = db.get(Document, state["document_id"])
        doc.doc_type, doc.status = result.doc_type, "processing"
        doc.doc_type_confidence, doc.doc_type_reason = result.confidence, result.reason
        db.commit()
        audit.record(db, "system", "document_classified", "document", doc.id, **result.audit())
        return {"doc_type": result.doc_type}

    def retrieve(state: State) -> State:
        chunks = _chunks(state["document_id"])
        text = " ".join(c.text for c in chunks)
        doc_emb = _mean_embedding(chunks)
        ranked = rank_rules(db, state["doc_type"], text, doc_emb)
        return {"rule_ids": [s.rule.id for s in ranked], "rule_scores": {s.rule.id: s.trace() for s in ranked}}

    def validate(state: State) -> State:
        doc_id = state["document_id"]
        vchunks = [VChunk(c.page, c.text) for c in _chunks(doc_id)]
        all_pages = sorted({c.page for c in vchunks})
        out: list[dict] = []
        for rid in state["rule_ids"]:
            rule = db.get(Rule, rid)
            res = run_rule_check(rule.check_type, rule.params or {}, vchunks)
            if res is not None:  # deterministic: the check scans every page
                explanation = res.explanation
                if res.passed is None:  # undeterminable: surface it for a human instead of staying silent
                    explanation = f"Could not verify automatically: {res.explanation} Manual review needed."
                out.append(dict(rule_id=rid, source="rule", passed=res.passed, missing=res.missing, explanation=explanation,
                                page=res.page, quote=res.quote, evidence=res.evidence, pages_checked=all_pages))
                continue
            # semantic rule -> LLM over retrieved evidence, then grounding check
            scored, method = evidence_chunks_for_rule(db, doc_id, rule)
            trace = dict(evidence_method=method, evidence_chunks=[
                {"chunk_id": c.id, "page": c.page, "similarity": None if sim is None else round(sim, 4),
                 "excerpt": c.text[:EXCERPT_CHARS]} for c, sim in scored])
            if not scored:
                out.append(dict(rule_id=rid, source="rule", passed=False, missing=True, page=None, quote=None, evidence=[],
                                pages_checked=all_pages, **trace,
                                explanation="No text relevant to this requirement was found in the document."))
                continue
            ev_chunks = [c for c, _ in scored]
            result = evaluate_semantic_rule(rid, rule.text, [VChunk(c.page, c.text) for c in ev_chunks])
            if result is not None:
                ev = [{"page": result["page"], "quote": result["quote"]}] if result["quote"] and result["page"] is not None else []
                out.append(dict(rule_id=rid, **result, evidence=ev,
                                pages_checked=sorted({c.page for c in ev_chunks}), **trace))
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
            status, action, needs_review = outcome(f["passed"], f.get("missing", False), rule.id, rule.title)
            trace = rule_trace(rule, state["doc_type"], state.get("rule_scores", {}).get(rule.id))
            if "evidence_method" in f:
                trace.update(evidence_method=f["evidence_method"], evidence_chunks=f["evidence_chunks"])
            findings.append({**f, "severity": sev, "title": title, "status": status, "recommended_action": action,
                             "needs_human_review": needs_review, "retrieval": trace})
        return {"findings": findings}

    def human_review(state: State) -> State:
        doc = db.get(Document, state["document_id"])
        for f in state["findings"]:
            db.add(Finding(
                project_id=doc.project_id, document_id=doc.id, rule_id=f["rule_id"], title=f["title"],
                severity=f["severity"], source=f["source"], evidence_page=f["page"], evidence_quote=f["quote"],
                explanation=f["explanation"], status=f["status"], evidence=f["evidence"],
                source_pages_checked=f["pages_checked"], recommended_action=f["recommended_action"],
                needs_human_review=f["needs_human_review"], retrieval=f["retrieval"], decision="pending",
            ))
        doc.status = "awaiting_review"  # pause: only a human can move findings out of 'pending'
        db.commit()
        # The full ranked rule list, including rules that produced no finding (needed for Recall@K).
        audit.record(db, "system", "workflow_completed", "document", doc.id, findings=len(state["findings"]),
                     doc_type=state["doc_type"], retrieved_rules=[{"rule_id": rid, **state.get("rule_scores", {}).get(rid, {})}
                                                                  for rid in state["rule_ids"]])
        return {}

    g = StateGraph(State)
    for name, fn in [("classify", classify), ("retrieve_rules", retrieve), ("validate_evidence", validate),
                     ("risk_assessment", assess_risk), ("human_review", human_review)]:
        g.add_node(name, _timed(name, fn))
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
