"""Document type classification: which kind of document this is decides which rules are checked.

Order of evidence, cheapest and most explainable first:
1. **Keyword hints, weighted by where they appear.** A hit in the title zone (the first lines of page 1) counts
   TITLE_WEIGHT times a hit in the body. *Why:* the title says what the document *is*; section headings and body
   text say what it *contains*. A construction plan with a "Design summary" section is still a construction plan
   (the 2026-11-12 sample was misclassified as design_summary, 3 body hits to 1 title hit, so every
   construction-only rule was skipped).
2. **Embedding tie-breaker** when two or more types are close: the document's mean chunk embedding is compared
   with a short description of each close type, and the nearest wins.
3. **Gemini**, only when no type has enough keyword evidence at all.

Every result carries a confidence (0-1) and a plain-language reason, stored on the document and shown in the UI.
Confidence is about the *type*, kept apart from the document's risk (blueprint section 7). The numbers are
heuristics, chosen to be easy to explain rather than calibrated; the reason says which path was taken.
"""
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

DOC_TYPE_HINTS = {
    "construction_plan": ["construction plan", "scope of work", "trenching", "splice plan"],
    "design_summary": ["design summary", "design basis", "cable schedule"],
    "as_built": ["as-built", "as built", "record drawing"],
    "permit": ["permit no", "permit number", "right-of-way permit"],
    "test_report": ["otdr", "test report", "insertion loss"],
}

# What each type is, for the embedding tie-breaker. Short and plain, so the comparison is about the kind of
# document rather than about particular wording.
TYPE_DESCRIPTIONS = {
    "construction_plan": "Fiber optic construction plan: how the route will be built, trenching and conduit, "
                         "installation methods, splicing, traffic control, utility locates and the work schedule.",
    "design_summary": "Fiber network design summary: design basis, fiber counts, cable schedule, route design, "
                      "splitter and splice architecture and capacity planning.",
    "as_built": "As-built record of installed fiber: record drawings of what was actually installed, final "
                "locations, measured lengths and deviations from the design.",
    "permit": "Permit for fiber construction: right-of-way or municipal permit with a permit number, "
              "conditions, issuing authority and validity dates.",
    "test_report": "Fiber test report: OTDR traces, insertion loss and power meter measurements, "
                   "pass/fail results per fiber.",
}

TITLE_LINES = 4  # non-empty lines at the start of page 1 that count as the title zone
TITLE_WEIGHT = 5
MIN_SCORE = 2  # weighted keyword score below this: not enough evidence, ask Gemini
CLEAR_RATIO = 1.5  # the leader wins on keywords alone if it beats the runner-up by this factor...
MIN_LEAD = 2  # ...and by at least this many points: a lead of one stray hit (2 to 1) is not decisive
MAX_KEYWORD_CONFIDENCE = 0.95  # keyword counting is never certain


@dataclass
class Classification:
    doc_type: str
    confidence: float
    method: str  # keyword | keyword+embedding | llm | none
    reason: str
    scores: dict[str, dict] = field(default_factory=dict)  # per type: title hits, body hits, weighted score

    def audit(self) -> dict:
        return {"doc_type": self.doc_type, "confidence": self.confidence, "method": self.method,
                "reason": self.reason, "scores": self.scores}


def split_title(first_page: str) -> tuple[str, str]:
    """(title zone, rest of page 1). The title zone is the first TITLE_LINES non-empty lines."""
    lines = first_page.splitlines()
    kept, n = [], 0
    for i, line in enumerate(lines):
        if line.strip():
            kept.append(line)
            n += 1
            if n == TITLE_LINES:
                return "\n".join(kept), "\n".join(lines[i + 1:])
    return "\n".join(kept), ""


def keyword_scores(pages: Sequence[str]) -> dict[str, dict]:
    """Hits per type in the title zone and in the body, and the weighted score."""
    title, rest = split_title(pages[0] if pages else "")
    title, body = title.lower(), " ".join([rest, *pages[1:]]).lower()
    out = {}
    for t, hints in DOC_TYPE_HINTS.items():
        th, bh = sum(title.count(h) for h in hints), sum(body.count(h) for h in hints)
        out[t] = {"title_hits": th, "body_hits": bh, "score": TITLE_WEIGHT * th + bh}
    return out


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = sum(x * x for x in a) ** 0.5, sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _label(t: str) -> str:
    return t.replace("_", " ")


def _hits(s: dict) -> str:
    parts = ([f"{s['title_hits']} in the title"] if s["title_hits"] else []) + \
            ([f"{s['body_hits']} in the text"] if s["body_hits"] else [])
    return ", ".join(parts) or "none"


def classify(pages: Sequence[str], doc_embedding: Sequence[float] | None = None,
             embed_types: Callable[[list[str]], list[list[float]]] | None = None,
             ask_llm: Callable[[str], str] | None = None) -> Classification:
    """Classify a document from its page texts (in reading order).

    `embed_types(texts)` embeds type descriptions (for the tie-breaker) and `ask_llm(excerpt)` returns a type from
    Gemini; both are optional and may raise, in which case the next-best evidence is used."""
    scores = keyword_scores(pages)
    ranked = sorted(scores, key=lambda t: scores[t]["score"], reverse=True)
    top, second = ranked[0], ranked[1]
    s1, s2 = scores[top]["score"], scores[second]["score"]

    if s1 >= MIN_SCORE and s1 >= CLEAR_RATIO * s2 and s1 - s2 >= MIN_LEAD:
        conf = round(min(MAX_KEYWORD_CONFIDENCE, s1 / (s1 + s2)), 2)
        reason = f"Keywords: {_label(top)} hints {_hits(scores[top])}"
        if s2:
            reason += f", against {_label(second)} {_hits(scores[second])}"
        return Classification(top, conf, "keyword", reason + ". Title hits count 5x.", scores)

    if s1 >= MIN_SCORE:  # a close call between two or more types
        close = [t for t in ranked if scores[t]["score"] and (scores[t]["score"] * CLEAR_RATIO >= s1 or s1 - scores[t]["score"] < MIN_LEAD)]
        names = " and ".join(_label(t) for t in close)
        if doc_embedding is not None and embed_types is not None:
            try:
                vecs = embed_types([TYPE_DESCRIPTIONS[t] for t in close])
                sims = {t: _cosine(doc_embedding, v) for t, v in zip(close, vecs)}
                best = max(sims, key=sims.get)
                gap = sims[best] - max(v for t, v in sims.items() if t != best)
                conf = round(0.5 + min(0.25, gap * 5), 2)  # a clear meaning gap (0.05 cosine) gives 0.75 at most
                reason = (f"Keywords were close between {names}; the text's meaning is nearest {_label(best)} "
                          f"(similarity {sims[best]:.2f} vs {sims[best] - gap:.2f}).")
                return Classification(best, conf, "keyword+embedding", reason,
                                      {**scores, **{t: {**scores[t], "similarity": round(v, 4)} for t, v in sims.items()}})
            except Exception:
                pass  # no tie-breaker available: fall through to the keyword leader
        conf = round(s1 / (s1 + s2), 2)
        return Classification(top, conf, "keyword", f"Keywords were close between {names}; "
                              f"{_label(top)} leads ({s1} to {s2}). Manual check advised.", scores)

    if ask_llm is not None:
        try:
            t = ask_llm(" ".join(pages)[:4000])
            return Classification(t, 0.6, "llm", f"Too few keyword hints; Gemini classified it as {_label(t)}.", scores)
        except Exception:
            pass
    return Classification("other", 0.0, "none", "Too few keyword hints and no model answer; type unknown.", scores)
