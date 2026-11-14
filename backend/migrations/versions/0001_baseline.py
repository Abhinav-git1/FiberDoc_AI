"""Baseline: the schema as it was before Alembic (8 tables, 2026-11-14).

An existing pre-Alembic database is not re-created: init_db brings it up to this shape with the old
idempotent ALTERs and then *stamps* it as 0001. A new, empty database runs this file.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DIM = 768  # fixed here on purpose: a migration must not change when settings do


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    tz = sa.DateTime(timezone=True)

    op.create_table(
        "users",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("location", sa.String, nullable=False),
        sa.Column("created_at", tz, nullable=False),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("doc_type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("page_count", sa.Integer, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("sha256", sa.String(64)),
        sa.Column("stored_path", sa.String),
        sa.Column("created_at", tz, nullable=False),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("document_id", sa.String, sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("page", sa.Integer, nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(DIM)),
    )
    op.create_table(
        "rules",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("applies_to", sa.JSON, nullable=False),
        sa.Column("keywords", sa.JSON, nullable=False),
        sa.Column("check_type", sa.String, nullable=False),
        sa.Column("params", sa.JSON, nullable=False),
        sa.Column("source_name", sa.String),
        sa.Column("section", sa.String),
        sa.Column("jurisdiction", sa.String),
        sa.Column("standard_family", sa.String),
        sa.Column("version", sa.String),
        sa.Column("effective_date", sa.String),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("embedding", Vector(DIM)),
    )
    op.create_table(
        "findings",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("project_id", sa.String, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("document_id", sa.String, sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("rule_id", sa.String, sa.ForeignKey("rules.id"), nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("evidence_page", sa.Integer),
        sa.Column("evidence_quote", sa.Text),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("status", sa.String),
        sa.Column("evidence", sa.JSON),
        sa.Column("source_pages_checked", sa.JSON),
        sa.Column("recommended_action", sa.Text),
        sa.Column("needs_human_review", sa.Boolean),
        sa.Column("retrieval", sa.JSON),
        sa.Column("decision", sa.String, nullable=False),
        sa.Column("created_at", tz, nullable=False),
    )
    op.create_table(
        "review_comments",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("finding_id", sa.String, sa.ForeignKey("findings.id"), nullable=False),
        sa.Column("author", sa.String, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("created_at", tz, nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("at", tz, nullable=False),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("entity", sa.String, nullable=False),
        sa.Column("entity_id", sa.String, nullable=False),
        sa.Column("detail", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    for t in ("audit_events", "review_comments", "findings", "rules", "chunks", "documents", "projects", "users"):
        op.drop_table(t)
