"""Hybrid rule retrieval: pgvector similarity + keyword overlap + doc-type metadata filter."""
import re

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


def retrieve_rules(db: Session, doc_type: str, doc_text: str, doc_embedding: list[float] | None, k: int = 20) -> list[Rule]:
    """Metadata filter (applies_to) -> vector ranking -> keyword boost. Returns up to k rules."""
    rules = [r for r in db.scalars(select(Rule)).all() if not r.applies_to or doc_type in r.applies_to]
    if not rules:
        return []
    doc_tokens = _tokens(doc_text)
    sim: dict[str, float] = {}
    if doc_embedding is not None:
        rows = db.execute(
            select(Rule.id, Rule.embedding.cosine_distance(doc_embedding)).where(Rule.id.in_([r.id for r in rules]))
        ).all()
        sim = {rid: 1.0 - float(dist) for rid, dist in rows if dist is not None}

    def score(r: Rule) -> float:
        kw = [w.lower() for w in (r.keywords or [])]
        kw_hit = sum(1 for w in kw if w in doc_tokens or w in doc_text.lower()) / len(kw) if kw else 0.0
        return 0.7 * sim.get(r.id, 0.0) + 0.3 * kw_hit

    return sorted(rules, key=score, reverse=True)[:k]


def top_chunks_for_rule(db: Session, document_id: str, rule: Rule, k: int = 4) -> list[Chunk]:
    """Semantic evidence retrieval: the document chunks most similar to the rule."""
    if rule.embedding is not None:
        stmt = (
            select(Chunk)
            .where(Chunk.document_id == document_id, Chunk.embedding.is_not(None))
            .order_by(Chunk.embedding.cosine_distance(rule.embedding))
            .limit(k)
        )
        found = list(db.scalars(stmt))
        if found:
            return found
    # fallback: keyword match
    kws = [w.lower() for w in (rule.keywords or [])]
    chunks = db.scalars(select(Chunk).where(Chunk.document_id == document_id)).all()
    return [c for c in chunks if any(w in c.text.lower() for w in kws)][:k]
