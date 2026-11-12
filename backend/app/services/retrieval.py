"""Hybrid rule retrieval: pgvector similarity + keyword overlap + doc-type metadata filter."""
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Rule
from app.services.llm import get_llm


def embed_document_chunks(db: Session, document_id: str) -> None:
    chunks = db.scalars(select(Chunk).where(Chunk.document_id == document_id)).all()
    if not chunks:
        return
    vectors = get_llm().embed([c.text for c in chunks])
    for c, v in zip(chunks, vectors):
        c.embedding = v
    db.commit()


def embed_rules(db: Session) -> None:
    rules = db.scalars(select(Rule).where(Rule.embedding.is_(None))).all()
    if not rules:
        return
    vectors = get_llm().embed([f"{r.title}. {r.text}" for r in rules])
    for r, v in zip(rules, vectors):
        r.embedding = v
    db.commit()


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", s.lower()))


@dataclass
class ScoredRule:
    rule: Rule
    rank: int  # 1 = best
    vector: float  # cosine similarity of the rule to the document (0 when either has no embedding)
    keyword: float  # share of the rule's keywords found in the document
    score: float  # 0.7 * vector + 0.3 * keyword

    def trace(self) -> dict:
        return {"rank": self.rank, "score": round(self.score, 4), "vector": round(self.vector, 4), "keyword": round(self.keyword, 4)}


def rank_rules(db: Session, doc_type: str, doc_text: str, doc_embedding: list[float] | None, k: int = 20,
               jurisdiction: str | None = None, standard_family: str | None = None) -> list[ScoredRule]:
    """Metadata filters (approved status, document type, optional jurisdiction / standard family) -> vector ranking
    -> keyword boost. Returns up to k rules with their scores. Filters run BEFORE ranking, so a retired or
    out-of-scope rule can never be retrieved however similar it is."""
    stmt = select(Rule).where(Rule.status == "approved")
    if jurisdiction:
        stmt = stmt.where(Rule.jurisdiction == jurisdiction)
    if standard_family:
        stmt = stmt.where(Rule.standard_family == standard_family)
    rules = [r for r in db.scalars(stmt).all() if not r.applies_to or doc_type in r.applies_to]
    if not rules:
        return []
    doc_tokens = _tokens(doc_text)
    low_text = doc_text.lower()
    sim: dict[str, float] = {}
    if doc_embedding is not None:
        rows = db.execute(
            select(Rule.id, Rule.embedding.cosine_distance(doc_embedding)).where(Rule.id.in_([r.id for r in rules]))
        ).all()
        sim = {rid: 1.0 - float(dist) for rid, dist in rows if dist is not None}

    def kw_hit(r: Rule) -> float:
        kw = [w.lower() for w in (r.keywords or [])]
        return sum(1 for w in kw if w in doc_tokens or w in low_text) / len(kw) if kw else 0.0

    scored = [(r, sim.get(r.id, 0.0), kw_hit(r)) for r in rules]
    scored.sort(key=lambda t: 0.7 * t[1] + 0.3 * t[2], reverse=True)
    return [ScoredRule(r, i + 1, v, kw, 0.7 * v + 0.3 * kw) for i, (r, v, kw) in enumerate(scored[:k])]


def retrieve_rules(db: Session, doc_type: str, doc_text: str, doc_embedding: list[float] | None, k: int = 20,
                   jurisdiction: str | None = None, standard_family: str | None = None) -> list[Rule]:
    """`rank_rules` without the scores."""
    return [s.rule for s in rank_rules(db, doc_type, doc_text, doc_embedding, k, jurisdiction, standard_family)]


def evidence_chunks_for_rule(db: Session, document_id: str, rule: Rule, k: int = 4) -> tuple[list[tuple[Chunk, float | None]], str]:
    """Semantic evidence retrieval: the document chunks most similar to the rule, each with its cosine similarity,
    plus the method used ("vector", or "keyword" when embeddings are missing; keyword hits have no score)."""
    if rule.embedding is not None:
        dist = Chunk.embedding.cosine_distance(rule.embedding)
        stmt = (
            select(Chunk, dist)
            .where(Chunk.document_id == document_id, Chunk.embedding.is_not(None))
            .order_by(dist)
            .limit(k)
        )
        found = [(c, 1.0 - float(d)) for c, d in db.execute(stmt).all()]
        if found:
            return found, "vector"
    kws = [w.lower() for w in (rule.keywords or [])]
    chunks = db.scalars(select(Chunk).where(Chunk.document_id == document_id)).all()
    return [(c, None) for c in chunks if any(w in c.text.lower() for w in kws)][:k], "keyword"


def top_chunks_for_rule(db: Session, document_id: str, rule: Rule, k: int = 4) -> list[Chunk]:
    """`evidence_chunks_for_rule` without the scores."""
    return [c for c, _ in evidence_chunks_for_rule(db, document_id, rule, k)[0]]
