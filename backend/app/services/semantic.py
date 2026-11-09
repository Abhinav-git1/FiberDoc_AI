"""Semantic (LLM) rule check: ask Gemini about ONE rule over supplied excerpts, then verify its quote.

Shared by the LangGraph `validate_evidence` node and the live evaluation tests.
"""
from app.schemas import EvidenceCheck
from app.services.llm import get_llm
from app.services.validators import Chunk, quote_is_grounded


def evaluate_semantic_rule(rule_id: str, rule_text: str, evidence: list[Chunk]) -> dict | None:
    """Return a raw finding dict (source/passed/explanation/page/quote), or None when the
    document complies WITH grounded evidence (no finding needed)."""
    context = "\n\n".join(f"[page {c.page}]\n{c.text}" for c in evidence)
    try:
        r = get_llm().generate_structured(
            "You check a fiber construction document against ONE rule.\n"
            f"Rule {rule_id}: {rule_text}\n\nDocument excerpts:\n{context}\n\n"
            "Rules for your answer: quote must be copied verbatim from the excerpts; "
            "never invent values; if the excerpts do not settle it, set complies='unclear'.",
            EvidenceCheck,
        )
    except Exception as e:  # LLM failure must not fabricate a result
        return dict(source="ai", passed=None, page=None, quote=None,
                    explanation=f"Automatic interpretation failed ({type(e).__name__}); manual review needed.")
    grounded = quote_is_grounded(r.quote, evidence)
    quote, page = (r.quote, r.page) if grounded else (None, None)
    if r.complies == "yes" and grounded:
        return None  # compliant with evidence: no finding
    return dict(source="ai", passed=None if r.complies == "unclear" else False,
                explanation=r.explanation if grounded or r.complies != "yes" else "Evidence could not be verified.",
                page=page, quote=quote)
