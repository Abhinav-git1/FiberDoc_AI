"""Semantic (LLM) rule check: ask Gemini about ONE rule over supplied excerpts, then verify its quote.

Shared by the LangGraph `validate_evidence` node and the live evaluation tests.
"""
from app.schemas import EvidenceCheck
from app.services.llm import get_llm
from app.services.validators import Chunk, quote_is_grounded


def evaluate_semantic_rule(rule_id: str, rule_text: str, evidence: list[Chunk]) -> dict | None:
    """Return a raw finding dict (source/passed/missing/explanation/page/quote), or None when the
    document complies WITH grounded evidence (no finding needed).

    Only a grounded quote can make a result definite. A "complies" or "violates" answer whose quote is not in the
    excerpts becomes undecided (needs review): an uncited claim is not accepted as a result."""
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
        return dict(source="ai", passed=None, missing=False, page=None, quote=None,
                    explanation=f"Automatic interpretation failed ({type(e).__name__}); manual review needed.")
    grounded = quote_is_grounded(r.quote, evidence)
    quote, page = (r.quote, r.page) if grounded else (None, None)
    if r.complies == "yes" and grounded:
        return None  # compliant with evidence: no finding
    if r.complies == "no" and grounded:
        return dict(source="ai", passed=False, missing=False, explanation=r.explanation, page=page, quote=quote)
    if r.complies == "no" and not r.found_relevant_text:
        return dict(source="ai", passed=False, missing=True, explanation=r.explanation, page=None, quote=None)
    if r.complies == "unclear":
        return dict(source="ai", passed=None, missing=False, explanation=r.explanation, page=page, quote=quote)
    # "yes" or "no" without a quote that appears in the excerpts
    return dict(source="ai", passed=None, missing=False, page=None, quote=None,
                explanation=f"The AI answered '{r.complies}', but its quote could not be found in the document, "
                            f"so the answer was not accepted. Its reasoning: {r.explanation}")
