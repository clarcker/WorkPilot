"""初始化完整数据库 schema

Revision ID: 0001
Revises:
Create Date: 2026-06-01
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 0. 扩展
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid()

    # ------------------------------------------------------------------
    # 1. 枚举类型
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TYPE user_role AS ENUM ('super_admin', 'dept_admin', 'employee')
    """)
    op.execute("""
        CREATE TYPE doc_visibility AS ENUM (
            'global', 'non_customer', 'dept_only', 'specific_users'
        )
    """)
    op.execute("""
        CREATE TYPE doc_status AS ENUM ('processing', 'ready', 'failed', 'archived')
    """)
    op.execute("""
        CREATE TYPE conversation_status AS ENUM ('active', 'archived')
    """)
    op.execute("""
        CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system')
    """)

    # ------------------------------------------------------------------
    # 2. departments
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE departments (
            id         SERIAL PRIMARY KEY,
            dept_code  VARCHAR(20)  NOT NULL UNIQUE,
            dept_name  VARCHAR(100) NOT NULL,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)

    # ------------------------------------------------------------------
    # 3. users
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE users (
            id                    SERIAL PRIMARY KEY,
            username              VARCHAR(50)  NOT NULL UNIQUE,
            employee_no           VARCHAR(20)  NOT NULL UNIQUE,
            display_name          VARCHAR(100) NOT NULL,
            real_name             VARCHAR(100) NOT NULL,
            dept_id               INT          REFERENCES departments(id),
            role                  user_role    NOT NULL DEFAULT 'employee',
            password_hash         VARCHAR(255) NOT NULL,
            must_change_password  BOOLEAN      NOT NULL DEFAULT TRUE,
            is_active             BOOLEAN      NOT NULL DEFAULT TRUE,
            failed_login_count    INT          NOT NULL DEFAULT 0,
            locked_at                   TIMESTAMPTZ,
            last_login_at               TIMESTAMPTZ,
            tokens_invalidated_before   TIMESTAMPTZ,
            email                 VARCHAR(255),
            notes                 TEXT,
            created_by            INT          REFERENCES users(id),
            created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_users_dept_id     ON users(dept_id)")
    op.execute("CREATE INDEX idx_users_role        ON users(role)")
    op.execute("CREATE INDEX idx_users_employee_no ON users(employee_no)")

    # ------------------------------------------------------------------
    # 4. revoked_tokens
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE revoked_tokens (
            jti        VARCHAR(100) PRIMARY KEY,
            revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL
        )
    """)

    # ------------------------------------------------------------------
    # 5. documents
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE documents (
            id            SERIAL PRIMARY KEY,
            file_uuid     UUID          NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            file_name     VARCHAR(255)  NOT NULL,
            file_size     BIGINT        NOT NULL,
            file_type     VARCHAR(20)   NOT NULL,
            storage_path  VARCHAR(500)  NOT NULL,
            dept_id       INT           NOT NULL REFERENCES departments(id),
            visibility    doc_visibility NOT NULL DEFAULT 'dept_only',
            status        doc_status     NOT NULL DEFAULT 'processing',
            error_message TEXT,
            category      VARCHAR(100),
            version       VARCHAR(50),
            uploaded_by   INT           NOT NULL REFERENCES users(id),
            created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_documents_dept_id    ON documents(dept_id)")
    op.execute("CREATE INDEX idx_documents_status     ON documents(status)")
    op.execute("CREATE INDEX idx_documents_visibility ON documents(visibility)")

    # ------------------------------------------------------------------
    # 6. doc_permissions（指定人员白名单）
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE doc_permissions (
            doc_id     INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            user_id    INT NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
            granted_by INT NOT NULL REFERENCES users(id),
            granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (doc_id, user_id)
        )
    """)

    # ------------------------------------------------------------------
    # 7. doc_chunks
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE doc_chunks (
            id          SERIAL PRIMARY KEY,
            doc_id      INT  NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INT  NOT NULL,
            content     TEXT NOT NULL,
            page_no     INT,
            heading     TEXT,
            token_count INT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_doc_chunks_doc_id ON doc_chunks(doc_id)")

    # ------------------------------------------------------------------
    # 8. embeddings（pgvector 768 维，HNSW 索引）
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE embeddings (
            id         SERIAL PRIMARY KEY,
            chunk_id   INT          NOT NULL UNIQUE REFERENCES doc_chunks(id) ON DELETE CASCADE,
            doc_id     INT          NOT NULL REFERENCES documents(id)         ON DELETE CASCADE,
            dept_id    INT          NOT NULL,
            embedding  vector(768)  NOT NULL,
            model_name VARCHAR(100) NOT NULL,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_embeddings_doc_id  ON embeddings(doc_id)")
    op.execute("CREATE INDEX idx_embeddings_dept_id ON embeddings(dept_id)")
    # HNSW 索引：m=16（每层最大连接数），ef_construction=64（构建时搜索宽度）
    # 余弦距离适合归一化的文本 embedding
    op.execute("""
        CREATE INDEX idx_embeddings_vector
            ON embeddings
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
    """)

    # ------------------------------------------------------------------
    # 9. conversations
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE conversations (
            id            SERIAL PRIMARY KEY,
            user_id       INT                 NOT NULL REFERENCES users(id),
            title         VARCHAR(255),
            status        conversation_status NOT NULL DEFAULT 'active',
            message_count INT                 NOT NULL DEFAULT 0,
            created_at    TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ         NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_conversations_user_id
            ON conversations(user_id, status, updated_at DESC)
    """)

    # ------------------------------------------------------------------
    # 10. messages
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE messages (
            id              SERIAL       PRIMARY KEY,
            conversation_id INT          NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role            message_role NOT NULL,
            content         TEXT         NOT NULL,
            sources         JSONB,
            input_tokens    INT,
            output_tokens   INT,
            latency_ms      INT,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_messages_conversation_id
            ON messages(conversation_id, created_at)
    """)

    # ------------------------------------------------------------------
    # 11. audit_logs（不可删除，无外键）
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE audit_logs (
            id            BIGSERIAL    PRIMARY KEY,
            operator_id   INT,
            operator_name VARCHAR(100) NOT NULL,
            action        VARCHAR(100) NOT NULL,
            resource_type VARCHAR(50),
            resource_id   VARCHAR(100),
            old_value     JSONB,
            new_value     JSONB,
            ip_address    INET,
            result        VARCHAR(20)  NOT NULL DEFAULT 'success',
            detail        TEXT,
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_audit_logs_operator_id ON audit_logs(operator_id)")
    op.execute("CREATE INDEX idx_audit_logs_action      ON audit_logs(action)")
    op.execute("CREATE INDEX idx_audit_logs_created_at  ON audit_logs(created_at DESC)")
    op.execute("CREATE INDEX idx_audit_logs_resource    ON audit_logs(resource_type, resource_id)")

    # ------------------------------------------------------------------
    # 12. system_config
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE system_config (
            key        VARCHAR(100) PRIMARY KEY,
            value      JSONB        NOT NULL,
            updated_by INT,
            updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)

    # 写入默认配置
    op.execute("""
        INSERT INTO system_config (key, value) VALUES
            ('max_sessions_per_user',      '200'),
            ('max_messages_per_session',   '500'),
            ('archive_retention_days',     '180'),
            ('login_max_fail_count',       '5'),
            ('chat_history_context_count', '5'),
            ('embed_model',                '"nomic-embed-text"'),
            ('chat_model_employee',        '"qwen2.5:7b"'),
            ('chat_model_admin',           '"deepseek-chat"')
    """)

    # ------------------------------------------------------------------
    # 13. 超级管理员内置账号
    #     初始密码：Admin@123（bcrypt，首次登录强制修改）
    #     bcrypt hash 在应用启动脚本中生成后通过 seed 写入，
    #     此处插入占位符，由 seed 脚本覆盖。
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO users (
            username, employee_no, display_name, real_name,
            role, password_hash, must_change_password, is_active
        ) VALUES (
            'admin',
            'ADMIN001',
            '超级管理员',
            '超级管理员',
            'super_admin',
            '$2b$12$placeholder_run_seed_to_set_real_password',
            TRUE,
            TRUE
        )
    """)


def downgrade() -> None:
    # 逆序删除
    op.execute("DROP TABLE IF EXISTS system_config    CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_logs       CASCADE")
    op.execute("DROP TABLE IF EXISTS messages         CASCADE")
    op.execute("DROP TABLE IF EXISTS conversations    CASCADE")
    op.execute("DROP TABLE IF EXISTS embeddings       CASCADE")
    op.execute("DROP TABLE IF EXISTS doc_chunks       CASCADE")
    op.execute("DROP TABLE IF EXISTS doc_permissions  CASCADE")
    op.execute("DROP TABLE IF EXISTS documents        CASCADE")
    op.execute("DROP TABLE IF EXISTS revoked_tokens   CASCADE")
    op.execute("DROP TABLE IF EXISTS users            CASCADE")
    op.execute("DROP TABLE IF EXISTS departments      CASCADE")

    op.execute("DROP TYPE IF EXISTS message_role        CASCADE")
    op.execute("DROP TYPE IF EXISTS conversation_status CASCADE")
    op.execute("DROP TYPE IF EXISTS doc_status          CASCADE")
    op.execute("DROP TYPE IF EXISTS doc_visibility      CASCADE")
    op.execute("DROP TYPE IF EXISTS user_role           CASCADE")
