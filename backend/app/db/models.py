"""Users · Projects · Documents · Chunks · Rules · Findings · Reviews · Audit events · Chats.

Changing a table? Add an Alembic migration too (see migrations/README.md)."""
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
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
    # required_term | numeric_min | numeric_max | consistency | semantic
    check_type: Mapped[str] = mapped_column(String, default="semantic")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    # Catalogue metadata (all demo values; see seed_rules.CATALOGUE). Used to filter retrieval and to cite the source.
    source_name: Mapped[str | None] = mapped_column(String, nullable=True)
    section: Mapped[str | None] = mapped_column(String, nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String, nullable=True)
    standard_family: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[str | None] = mapped_column(String, nullable=True)
    effective_date: Mapped[str | None] = mapped_column(String, nullable=True)  # ISO date
    status: Mapped[str] = mapped_column(String, default="approved")  # approved | draft | retired; only approved rules are retrieved
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
    # Outcome of the automatic check, separate from the human `decision`: passed | failed | missing_evidence | needs_review.
    # Nullable because findings created before these columns existed don't have them.
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{page, quote}]; evidence_page/quote = first item
    source_pages_checked: Mapped[list | None] = mapped_column(JSON, nullable=True)  # pages the check looked at
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_human_review: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # automation could not settle it
    # Retrieval trace: the rule as used (id, version, source, text), its ranking scores, and for semantic rules
    # the document chunks given to the LLM. See graph.validate.
    retrieval: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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


class Chat(Base):
    __tablename__ = "chats"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # set once auth exists
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String, default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)  # orders "Recent chats"
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_chat_id_created_at", "chat_id", "created_at"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String)  # user | assistant
    text: Mapped[str] = mapped_column(Text)
    # The upload this message is about (opens its result panel). Kept if the document is deleted, minus the link.
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String, default="text")  # text | upload | result | error
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    chat: Mapped[Chat] = relationship(back_populates="messages")
