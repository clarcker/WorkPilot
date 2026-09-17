"""doc_chunks.content_tsv 全文检索列（R3）

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-17
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS content_tsv tsvector"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_chunks_tsv "
        "ON doc_chunks USING GIN (content_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_doc_chunks_tsv")
    op.execute("ALTER TABLE doc_chunks DROP COLUMN IF EXISTS content_tsv")
