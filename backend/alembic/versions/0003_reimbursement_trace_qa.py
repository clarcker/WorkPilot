"""报销业务表 + agent_traces + qa_records + users.job_level

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users.job_level
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS job_level VARCHAR(20) NOT NULL DEFAULT 'mid'
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS reimbursement_rules (
            id          SERIAL PRIMARY KEY,
            category    VARCHAR(50)  NOT NULL,
            job_level   VARCHAR(20)  NOT NULL,
            daily_max   INTEGER      NOT NULL,
            annual_max  INTEGER      NOT NULL,
            doc_ref     VARCHAR(255)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_rules_cat_level "
        "ON reimbursement_rules (category, job_level)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS reimbursement_limits (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            category    VARCHAR(50) NOT NULL,
            annual_max  INTEGER NOT NULL,
            used        INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_limit_user_cat "
        "ON reimbursement_limits (user_id, category)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS reimbursement_requests (
            id               BIGSERIAL PRIMARY KEY,
            request_no       VARCHAR(50)  NOT NULL UNIQUE,
            user_id          INTEGER      NOT NULL REFERENCES users(id),
            dept_id          INTEGER      REFERENCES departments(id),
            category         VARCHAR(50)  NOT NULL,
            amount           INTEGER      NOT NULL,
            days             INTEGER,
            trip_start       VARCHAR(20),
            trip_end         VARCHAR(20),
            approval_ref     VARCHAR(50),
            precheck_result  JSONB,
            status           VARCHAR(20)  NOT NULL DEFAULT 'draft',
            idempotency_key  VARCHAR(255) NOT NULL UNIQUE,
            approver_id      INTEGER,
            approver_comment TEXT,
            decided_at       TIMESTAMPTZ,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reimb_user_status "
        "ON reimbursement_requests (user_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reimb_dept_status "
        "ON reimbursement_requests (dept_id, status)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_traces (
            id               BIGSERIAL PRIMARY KEY,
            conversation_id  INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
            user_id          INTEGER NOT NULL,
            query            TEXT NOT NULL,
            intent           VARCHAR(20),
            rewritten_query  TEXT,
            steps            JSONB NOT NULL DEFAULT '[]'::jsonb,
            tool_calls       JSONB,
            final_answer     TEXT,
            sources          JSONB,
            llm_model        VARCHAR(100),
            total_latency_ms INTEGER,
            error            TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_traces_user "
        "ON agent_traces (user_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_traces_conv "
        "ON agent_traces (conversation_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS qa_records (
            id               BIGSERIAL PRIMARY KEY,
            conversation_id  INTEGER,
            user_id          INTEGER NOT NULL,
            dept_id          INTEGER,
            query            TEXT NOT NULL,
            intent           VARCHAR(20),
            top1_score       DOUBLE PRECISION,
            doc_hit          BOOLEAN NOT NULL DEFAULT FALSE,
            answer_preview   TEXT,
            feedback         VARCHAR(10),
            feedback_reason  VARCHAR(50),
            latency_ms       INTEGER,
            is_gap           BOOLEAN NOT NULL DEFAULT FALSE,
            gap_resolved     BOOLEAN NOT NULL DEFAULT FALSE,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_qa_user_created "
        "ON qa_records (user_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_qa_gap "
        "ON qa_records (is_gap, gap_resolved)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS qa_records")
    op.execute("DROP TABLE IF EXISTS agent_traces")
    op.execute("DROP TABLE IF EXISTS reimbursement_requests")
    op.execute("DROP TABLE IF EXISTS reimbursement_limits")
    op.execute("DROP TABLE IF EXISTS reimbursement_rules")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS job_level")
