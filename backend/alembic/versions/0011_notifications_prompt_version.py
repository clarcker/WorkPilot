"""notifications + prompt_set_version + active_embedding_model

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-21
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title VARCHAR(255) NOT NULL,
            body TEXT NOT NULL,
            level VARCHAR(20) NOT NULL DEFAULT 'info',
            source VARCHAR(50) NOT NULL DEFAULT 'system',
            payload JSONB,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notifications_user "
        "ON notifications (user_id, is_read, created_at)"
    )
    op.execute(
        "ALTER TABLE agent_traces ADD COLUMN IF NOT EXISTS prompt_set_version VARCHAR(32)"
    )
    op.execute(
        "ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS prompt_set_version VARCHAR(32)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS prompt_set_version")
    op.execute("ALTER TABLE agent_traces DROP COLUMN IF EXISTS prompt_set_version")
    op.execute("DROP TABLE IF EXISTS notifications")
