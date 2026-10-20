"""documents.lifecycle + effective_date + supersedes_doc_id

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE doc_lifecycle AS ENUM ('effective', 'superseded', 'draft');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS lifecycle "
        "doc_lifecycle NOT NULL DEFAULT 'effective'"
    )
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS effective_date DATE"
    )
    op.execute(
        "ALTER TABLE documents ADD COLUMN IF NOT EXISTS supersedes_doc_id "
        "INTEGER REFERENCES documents(id) ON DELETE SET NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_documents_lifecycle ON documents (lifecycle)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_documents_supersedes ON documents (supersedes_doc_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_supersedes")
    op.execute("DROP INDEX IF EXISTS idx_documents_lifecycle")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS supersedes_doc_id")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS effective_date")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS lifecycle")
    op.execute("DROP TYPE IF EXISTS doc_lifecycle")
