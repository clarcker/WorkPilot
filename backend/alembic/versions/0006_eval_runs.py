"""eval_runs 评测结果落库表

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS eval_runs (
            id                     BIGSERIAL PRIMARY KEY,
            started_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at            TIMESTAMPTZ,
            total_cases            INTEGER NOT NULL DEFAULT 0,
            scored_cases           INTEGER NOT NULL DEFAULT 0,
            timeout_count          INTEGER NOT NULL DEFAULT 0,
            intent_accuracy        DOUBLE PRECISION,
            doc_hit_rate           DOUBLE PRECISION,
            tool_call_accuracy     DOUBLE PRECISION,
            citation_rate          DOUBLE PRECISION,
            permission_pass_rate   DOUBLE PRECISION,
            avg_latency_ms         INTEGER,
            skip_generation        BOOLEAN NOT NULL DEFAULT TRUE,
            tool_dry_run           BOOLEAN NOT NULL DEFAULT TRUE,
            case_results           JSONB,
            failed_cases           JSONB,
            operator_id            INTEGER,
            note                   VARCHAR(255)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_runs_started "
        "ON eval_runs (started_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS eval_runs")
