"""eval_runs 新增 recall/mrr/heading 列（E2）

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-18
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS recall_at_1 DOUBLE PRECISION")
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS mrr DOUBLE PRECISION")
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS heading_hit_rate DOUBLE PRECISION")


def downgrade() -> None:
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS recall_at_1")
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS mrr")
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS heading_hit_rate")
