"""it_tickets 增加处理备注与处理人

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-17
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE it_tickets ADD COLUMN IF NOT EXISTS handle_note TEXT")
    op.execute("ALTER TABLE it_tickets ADD COLUMN IF NOT EXISTS handler_id INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE it_tickets DROP COLUMN IF EXISTS handle_note")
    op.execute("ALTER TABLE it_tickets DROP COLUMN IF EXISTS handler_id")
