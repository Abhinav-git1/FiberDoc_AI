from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Finding, ReviewComment
from app.db.session import get_db
from app.schemas import CommentOut, EvidenceOut, FindingOut, ReviewIn
from app.services import audit

router = APIRouter(prefix="/api")


def to_out(f: Finding) -> FindingOut:
    return FindingOut(
        id=f.id, project_id=f.project_id, doc_name=f.document.name, title=f.title, severity=f.severity,
        source=f.source, rule_id=f.rule_id, rule_text=f.rule.text,
        evidence=EvidenceOut(page=f.evidence_page, quote=f.evidence_quote) if f.evidence_quote and f.evidence_page else None,
        explanation=f.explanation, decision=f.decision,
        comments=[CommentOut(id=c.id, author=c.author, text=c.text, at=c.created_at.date().isoformat()) for c in f.comments],
    )


@router.get("/findings", response_model=list[FindingOut], response_model_by_alias=True)
def list_findings(project_id: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Finding).order_by(Finding.created_at)
    if project_id:
        stmt = stmt.where(Finding.project_id == project_id)
    return [to_out(f) for f in db.scalars(stmt)]


@router.post("/findings/{finding_id}/review", response_model=FindingOut, response_model_by_alias=True)
def review_finding(finding_id: str, body: ReviewIn, db: Session = Depends(get_db)):
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    before = f.decision
    f.decision = body.decision  # the ONLY place a decision is set: always by a human
    if body.comment.strip():
        f.comments.append(ReviewComment(author="Reviewer", text=body.comment.strip()))
    db.commit()
    audit.record(db, "Reviewer", "finding_reviewed", "finding", f.id, before=before, after=body.decision)
    return to_out(f)
