"""eval_cases golden case 持久化表

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-18
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS eval_cases (
            id          BIGSERIAL PRIMARY KEY,
            case_id     VARCHAR(50) NOT NULL UNIQUE,
            question    TEXT NOT NULL,
            "group"     VARCHAR(50),
            payload     JSONB NOT NULL,
            source      VARCHAR(20) NOT NULL DEFAULT 'seed',
            active      BOOLEAN NOT NULL DEFAULT TRUE,
            created_by  INTEGER,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_eval_cases_group ON eval_cases (\"group\")")
    op.execute("CREATE INDEX IF NOT EXISTS idx_eval_cases_active ON eval_cases (active)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS eval_cases")
