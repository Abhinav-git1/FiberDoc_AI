"""Users · Projects · Documents · Chunks · Rules · Findings · Reviews · Audit events."""
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db.session import Base

DIM = get_settings().embed_dim


def _id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, default="Reviewer")
    role: Mapped[str] = mapped_column(String, default="reviewer")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    documents: Mapped[list["Document"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String)
    doc_type: Mapped[str] = mapped_column(String, default="unknown")
    status: Mapped[str] = mapped_column(String, default="uploaded")  # uploaded|processing|awaiting_review|error
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stored_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    project: Mapped[Project] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    page: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String, default="text")  # text|table
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIM), nullable=True)
    document: Mapped[Document] = relationship(back_populates="chunks")


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. QA-014
    title: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String, default="medium")
    applies_to: Mapped[list] = mapped_column(JSON, default=list)  # doc types; [] = all
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    # required_term | numeric_min | consistency | semantic
    check_type: Mapped[str] = mapped_column(String, default="semantic")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(DIM), nullable=True)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"))
    title: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)  # rule | ai
    evidence_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    document: Mapped[Document] = relationship()
    rule: Mapped[Rule] = relationship()
    comments: Mapped[list["ReviewComment"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan", order_by="ReviewComment.created_at"
    )


class ReviewComment(Base):
    __tablename__ = "review_comments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"))
    author: Mapped[str] = mapped_column(String, default="Reviewer")
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finding: Mapped[Finding] = relationship(back_populates="comments")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    actor: Mapped[str] = mapped_column(String)  # user id/name or "system"
    action: Mapped[str] = mapped_column(String)
    entity: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
