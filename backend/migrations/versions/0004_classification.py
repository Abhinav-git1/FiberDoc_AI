"""Classification confidence on documents; reading order of chunks.

- documents.doc_type_confidence / doc_type_reason: how sure the classifier was and why (app/services/classifier.py).
  Kept apart from the risk score, as the blueprint asks (section 7). NULL for documents classified before 2026-11-19.
- chunks.seq: the chunk's position in the parsed document. Chunk ids are random, so without it the order of chunks
  within a page was undefined, and "the first lines of page 1" (the title zone the classifier weights) could not be
  found reliably. NULL for older chunks; they sort after numbered ones.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("doc_type_confidence", sa.Float))
    op.add_column("documents", sa.Column("doc_type_reason", sa.Text))
    op.add_column("chunks", sa.Column("seq", sa.Integer))


def downgrade() -> None:
    op.drop_column("chunks", "seq")
    op.drop_column("documents", "doc_type_reason")
    op.drop_column("documents", "doc_type_confidence")
