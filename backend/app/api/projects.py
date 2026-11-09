from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Chunk, Document, Project
from app.db.session import SessionLocal, get_db
from app.schemas import DocumentOut, ProjectIn, ProjectOut
from app.services import audit
from app.services.document_parser import parse_document, validate_upload
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


def _process(document_id: str, path: Path) -> None:  # path is the stored original; it is kept
    """Background job: parse -> chunk -> embed -> LangGraph workflow."""
    with SessionLocal() as db:
        try:
            parsed = parse_document(path)
            doc = db.get(Document, document_id)
            doc.page_count = parsed.page_count
            db.add_all(Chunk(document_id=document_id, page=c.page, kind=c.kind, text=c.text) for c in parsed.chunks)
            db.commit()
            embed_document_chunks(db, document_id)
            run_workflow(db, document_id)
        except Exception as e:
            db.rollback()
            doc = db.get(Document, document_id)
            doc.status, doc.error = "error", str(e)[:500]
            db.commit()


@router.post("/projects/{project_id}/documents", response_model=DocumentOut, response_model_by_alias=True, status_code=202)
async def upload_document(project_id: str, background: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "Project not found")
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
    background.add_task(_process, doc.id, stored)
    return doc
