from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AuditEvent, Chat, Chunk, Document, Project
from app.db.session import SessionLocal, get_db
from app.schemas import DocumentOut, ProjectIn, ProjectOut, TimingsOut
from app.services import audit, timing
from app.services.chat_log import add_message, record_outcome
from app.services.document_parser import parse_document, validate_upload
from app.services.notify import notify_document_checked
from app.services.retrieval import embed_document_chunks
from app.services.storage import sha256_hex, store_original
from app.workflow.graph import run_workflow

router = APIRouter(prefix="/api")


def _project_out(db: Session, p: Project) -> ProjectOut:
    n = db.scalar(select(func.count()).select_from(Document).where(Document.project_id == p.id)) or 0
    return ProjectOut(id=p.id, name=p.name, location=p.location, doc_count=n)


@router.get("/projects", response_model=list[ProjectOut], response_model_by_alias=True)
def list_projects(db: Session = Depends(get_db)):
    return [_project_out(db, p) for p in db.scalars(select(Project).order_by(Project.created_at))]


@router.post("/projects", response_model=ProjectOut, response_model_by_alias=True, status_code=201)
def create_project(body: ProjectIn, db: Session = Depends(get_db)):
    p = Project(name=body.name, location=body.location)
    db.add(p)
    db.commit()
    audit.record(db, "user", "project_created", "project", p.id)
    return _project_out(db, p)


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut], response_model_by_alias=True)
def list_documents(project_id: str, db: Session = Depends(get_db)):
    return list(db.scalars(select(Document).where(Document.project_id == project_id).order_by(Document.created_at)))


@router.get("/documents/{document_id}/timings", response_model=TimingsOut, response_model_by_alias=True)
def document_timings(document_id: str, db: Session = Depends(get_db)):
    """The timing breakdown of the document's latest processing run. 404 while processing, or for documents
    processed before timings were recorded (2026-11-15)."""
    ev = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == document_id, AuditEvent.action == "processing_timed")
                    .order_by(AuditEvent.at.desc()).limit(1)).first()
    if ev is None:
        raise HTTPException(404, "No timings recorded for this document")
    return TimingsOut.model_validate(ev.detail)


def _process(document_id: str, path: Path) -> None:  # path is the stored original; it is kept
    """Background job: parse -> chunk -> embed -> LangGraph workflow."""
    with SessionLocal() as db, timing.track() as t:
        try:
            with timing.step("parse"):
                parsed = parse_document(path)
                doc = db.get(Document, document_id)
                doc.page_count = parsed.page_count
                db.add_all(Chunk(document_id=document_id, page=c.page, kind=c.kind, text=c.text) for c in parsed.chunks)
                db.commit()
            with timing.step("embed_chunks"):
                embed_document_chunks(db, document_id)
            run_workflow(db, document_id)  # each workflow node records its own step
        except Exception as e:
            db.rollback()
            doc = db.get(Document, document_id)
            doc.status, doc.error = "error", str(e)[:500]
            db.commit()
        # Where the time went, kept with the document's audit trail (GET /api/documents/{id}/timings).
        audit.record(db, "system", "processing_timed", "document", document_id, **t.summary())
        record_outcome(db, document_id)  # the result/error message for the chat it was uploaded from
        notify_document_checked(db, document_id)  # outbound webhook (n8n -> email), if switched on


INTERRUPTED = "Interrupted: the server restarted while this document was being processed. Please re-upload it."


def fail_interrupted(db: Session) -> int:
    """Run at startup. Processing happens in a background task inside the server process, so a restart kills it
    and the document would otherwise stay 'processing' forever (and the chat would keep polling)."""
    stuck = db.scalars(select(Document).where(Document.status == "processing")).all()
    for doc in stuck:
        doc.status, doc.error = "error", INTERRUPTED
    db.commit()
    for doc in stuck:
        record_outcome(db, doc.id)
    return len(stuck)


@router.post("/projects/{project_id}/documents", response_model=DocumentOut, response_model_by_alias=True, status_code=202)
async def upload_document(project_id: str, background: BackgroundTasks, file: UploadFile = File(...),
                          chat_id: str | None = Form(None), db: Session = Depends(get_db)):
    """`chat_id` (optional): the chat it was sent from. The upload and its result are then saved in that chat."""
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")
    chat = db.get(Chat, chat_id) if chat_id else None
    if chat_id and chat is None:
        raise HTTPException(404, "Chat not found")
    data = await file.read()
    name = Path(file.filename or "upload").name
    try:
        validate_upload(name, len(data), get_settings().max_upload_mb)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    digest = sha256_hex(data)
    duplicate = db.scalar(select(Document.id).where(Document.project_id == project_id, Document.sha256 == digest))
    doc = Document(project_id=project_id, name=name, status="processing", sha256=digest)
    db.add(doc)
    db.flush()  # assigns doc.id
    stored = store_original(Path(get_settings().upload_dir), project_id, doc.id, name, data)
    doc.stored_path = str(stored)
    db.commit()
    audit.record(db, "user", "document_uploaded", "document", doc.id, filename=name, sha256=digest, duplicate_of=duplicate)
    if chat is not None:
        add_message(db, chat, "user", name, "upload", doc.id)
    background.add_task(_process, doc.id, stored)
    return doc
