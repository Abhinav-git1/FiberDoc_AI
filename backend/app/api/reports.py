from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, Finding, Project
from app.db.session import get_db
from app.services import audit
from app.services.report import render_report

router = APIRouter(prefix="/api")


@router.get("/projects/{project_id}/report")
def project_report(project_id: str, db: Session = Depends(get_db)):
    """Downloadable validation summary (HTML) for one project. Open it and use Print -> Save as PDF if needed."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    documents = list(db.scalars(select(Document).where(Document.project_id == project_id).order_by(Document.created_at)))
    findings = list(db.scalars(select(Finding).where(Finding.project_id == project_id).order_by(Finding.created_at)))
    now = datetime.now(timezone.utc)
    html = render_report(project, documents, findings, now)
    audit.record(db, "user", "report_generated", "project", project_id, findings=len(findings))
    filename = f"validation-report-{project_id}-{now:%Y%m%d}.html"
    return Response(html, media_type="text/html; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
