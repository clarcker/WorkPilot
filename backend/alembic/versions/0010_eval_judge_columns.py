"""eval_runs Q3 judge 字段

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS judge_model VARCHAR(100)")
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS faithfulness_avg DOUBLE PRECISION")
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS points_coverage DOUBLE PRECISION")
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS hallucination_count INTEGER")
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS refusal_correct_rate DOUBLE PRECISION")
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS label VARCHAR(100)")
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS mode VARCHAR(20) DEFAULT 'fast'")
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0")
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'finished'")


def downgrade() -> None:
    for col in (
        "judge_model", "faithfulness_avg", "points_coverage",
        "hallucination_count", "refusal_correct_rate",
        "label", "mode", "progress", "status",
    ):
        op.execute(f"ALTER TABLE eval_runs DROP COLUMN IF EXISTS {col}")
