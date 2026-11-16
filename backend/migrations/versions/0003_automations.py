"""Automations: outbound webhook settings and the delivery log (n8n email integration).

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tz = sa.DateTime(timezone=True)
    op.create_table(
        "automation_settings",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("webhook_url", sa.String),
        sa.Column("recipient_email", sa.String),
        sa.Column("secret", sa.String, nullable=False),
        sa.Column("updated_at", tz, nullable=False),
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("document_id", sa.String, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("event", sa.String, nullable=False),
        sa.Column("url", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("http_status", sa.Integer),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", tz, nullable=False),
    )
    op.create_index("ix_webhook_deliveries_document_id", "webhook_deliveries", ["document_id"])
    op.create_index("ix_webhook_deliveries_created_at", "webhook_deliveries", ["created_at"])


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("automation_settings")
