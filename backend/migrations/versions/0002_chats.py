"""Chat storage: chats and chat_messages (docs/schema.md tables 10 and 11).

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tz = sa.DateTime(timezone=True)
    op.create_table(
        "chats",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.String, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.String, sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("created_at", tz, nullable=False),
        sa.Column("updated_at", tz, nullable=False),
    )
    op.create_index("ix_chats_user_id", "chats", ["user_id"])
    op.create_index("ix_chats_project_id", "chats", ["project_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("chat_id", sa.String, sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("document_id", sa.String, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("created_at", tz, nullable=False),
    )
    op.create_index("ix_chat_messages_chat_id_created_at", "chat_messages", ["chat_id", "created_at"])
    op.create_index("ix_chat_messages_document_id", "chat_messages", ["document_id"])


def downgrade() -> None:
    op.drop_table("chat_messages")  # its indexes go with it
    op.drop_table("chats")
