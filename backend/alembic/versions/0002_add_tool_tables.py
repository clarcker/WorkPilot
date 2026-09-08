"""添加工具调用记录表和 IT 工单表

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-25
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tool_calls (
            id              BIGSERIAL PRIMARY KEY,
            conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
            message_id      INTEGER REFERENCES messages(id) ON DELETE SET NULL,
            user_id         INTEGER NOT NULL,
            tool_name       VARCHAR(100) NOT NULL,
            tool_args       JSONB NOT NULL,
            tool_result     JSONB,
            allowed         BOOLEAN NOT NULL DEFAULT TRUE,
            deny_reason     TEXT,
            latency_ms      INTEGER,
            error           TEXT,
            idempotency_key VARCHAR(255) UNIQUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_tool_calls_user_id    ON tool_calls (user_id)")
    op.execute("CREATE INDEX idx_tool_calls_tool_name  ON tool_calls (tool_name)")
    op.execute("CREATE INDEX idx_tool_calls_created_at ON tool_calls (created_at)")

    op.execute("""
        CREATE TABLE it_tickets (
            id              BIGSERIAL PRIMARY KEY,
            ticket_no       VARCHAR(50) NOT NULL UNIQUE,
            user_id         INTEGER NOT NULL,
            issue_type      VARCHAR(100) NOT NULL,
            description     TEXT NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'open',
            idempotency_key VARCHAR(255) NOT NULL UNIQUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_it_tickets_user_id ON it_tickets (user_id)")
    op.execute("CREATE INDEX idx_it_tickets_status  ON it_tickets (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS it_tickets")
    op.execute("DROP TABLE IF EXISTS tool_calls")