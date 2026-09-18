"""
WorkPilot v2 — 全部数据库模型
表顺序：departments → users → revoked_tokens → documents → doc_permissions
       → doc_chunks → embeddings → conversations → messages
       → audit_logs → system_config
"""

import datetime
import enum
from typing import Optional, List

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, Float, ForeignKey,
    Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from db.base import Base


# =============================================
# 枚举类型
# =============================================

class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    dept_admin  = "dept_admin"
    employee    = "employee"


class DocVisibility(str, enum.Enum):
    global_     = "global"          # 全体共享
    non_customer = "non_customer"   # 非客服共享
    dept_only   = "dept_only"       # 本部门共享
    specific_users = "specific_users"  # 本部门指定人员


class DocStatus(str, enum.Enum):
    processing = "processing"
    ready      = "ready"
    failed     = "failed"
    archived   = "archived"


class ConversationStatus(str, enum.Enum):
    active   = "active"
    archived = "archived"


class MessageRole(str, enum.Enum):
    user      = "user"
    assistant = "assistant"
    system    = "system"


# =============================================
# departments
# =============================================

class Department(Base):
    __tablename__ = "departments"

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True)
    dept_code:  Mapped[str]      = mapped_column(String(20),  nullable=False, unique=True)  # 'HR', 'RD'
    dept_name:  Mapped[str]      = mapped_column(String(100), nullable=False)               # '人力资源部'
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relations
    users:     Mapped[List["User"]]     = relationship(back_populates="department")
    documents: Mapped[List["Document"]] = relationship(back_populates="department")


# =============================================
# users
# =============================================

class User(Base):
    __tablename__ = "users"

    id:                   Mapped[int]           = mapped_column(Integer, primary_key=True)
    username:             Mapped[str]           = mapped_column(String(50),  nullable=False, unique=True)  # 全拼，不可修改
    employee_no:          Mapped[str]           = mapped_column(String(20),  nullable=False, unique=True)  # HR001
    display_name:         Mapped[str]           = mapped_column(String(100), nullable=False)               # 昵称
    real_name:            Mapped[str]           = mapped_column(String(100), nullable=False)               # 真实姓名
    dept_id:              Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True)
    role:                 Mapped[UserRole]      = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=UserRole.employee
    )
    # 职级：预审按职级取报销标准（junior / mid / senior / lead）
    job_level:            Mapped[str]           = mapped_column(String(20), nullable=False, default="mid")
    password_hash:        Mapped[str]           = mapped_column(String(255), nullable=False)
    must_change_password: Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    is_active:            Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count:   Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    locked_at:                  Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at:              Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 强制登出：该时间之前签发的所有 Token 均视为无效
    tokens_invalidated_before:  Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    email:                Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes:                Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by:           Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at:           Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at:           Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # relations
    department: Mapped[Optional["Department"]]    = relationship(back_populates="users")
    conversations: Mapped[List["Conversation"]]   = relationship(back_populates="user")
    uploaded_docs: Mapped[List["Document"]]       = relationship(
        back_populates="uploaded_by_user", foreign_keys="Document.uploaded_by"
    )
    doc_permissions: Mapped[List["DocPermission"]] = relationship(
        back_populates="user", foreign_keys="DocPermission.user_id"
    )

    __table_args__ = (
        Index("idx_users_dept_id",    "dept_id"),
        Index("idx_users_role",       "role"),
        Index("idx_users_employee_no","employee_no"),
    )


# =============================================
# revoked_tokens（JWT 黑名单，强制登出）
# =============================================

class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti:        Mapped[str]              = mapped_column(String(100), primary_key=True)
    revoked_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# =============================================
# documents
# =============================================

class Document(Base):
    __tablename__ = "documents"

    id:           Mapped[int]        = mapped_column(Integer, primary_key=True)
    file_uuid:    Mapped[str]        = mapped_column(
        UUID(as_uuid=False), nullable=False, unique=True, server_default=func.gen_random_uuid()
    )
    file_name:    Mapped[str]        = mapped_column(String(255), nullable=False)
    file_size:    Mapped[int]        = mapped_column(BigInteger, nullable=False)   # bytes
    file_type:    Mapped[str]        = mapped_column(String(20),  nullable=False)  # 'pdf','docx','md'
    storage_path: Mapped[str]        = mapped_column(String(500), nullable=False)
    dept_id:      Mapped[int]        = mapped_column(ForeignKey("departments.id"), nullable=False)
    visibility:   Mapped[DocVisibility] = mapped_column(
        Enum(DocVisibility, name="doc_visibility", values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=DocVisibility.dept_only
    )
    status:       Mapped[DocStatus]  = mapped_column(
        Enum(DocStatus, name="doc_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=DocStatus.processing
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category:     Mapped[Optional[str]]  = mapped_column(String(100), nullable=True)
    version:      Mapped[Optional[str]]  = mapped_column(String(50),  nullable=True)
    uploaded_by:  Mapped[int]        = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at:   Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at:   Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # relations
    department:        Mapped["Department"]         = relationship(back_populates="documents")
    uploaded_by_user:  Mapped["User"]               = relationship(
        back_populates="uploaded_docs", foreign_keys=[uploaded_by]
    )
    permissions:       Mapped[List["DocPermission"]] = relationship(back_populates="document")
    chunks:            Mapped[List["DocChunk"]]      = relationship(back_populates="document")

    __table_args__ = (
        Index("idx_documents_dept_id",    "dept_id"),
        Index("idx_documents_status",     "status"),
        Index("idx_documents_visibility", "visibility"),
    )


# =============================================
# doc_permissions（指定人员白名单）
# =============================================

class DocPermission(Base):
    __tablename__ = "doc_permissions"

    doc_id:     Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    user_id:    Mapped[int] = mapped_column(ForeignKey("users.id",     ondelete="CASCADE"), primary_key=True)
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    granted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relations
    document: Mapped["Document"] = relationship(back_populates="permissions")
    user:     Mapped["User"]     = relationship(back_populates="doc_permissions", foreign_keys=[user_id])


# =============================================
# doc_chunks
# =============================================

class DocChunk(Base):
    __tablename__ = "doc_chunks"

    id:          Mapped[int]          = mapped_column(Integer, primary_key=True)
    doc_id:      Mapped[int]          = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int]          = mapped_column(Integer, nullable=False)
    content:     Mapped[str]          = mapped_column(Text,    nullable=False)
    page_no:     Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    heading:     Mapped[Optional[str]] = mapped_column(Text,    nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # R3：jieba 分词后的全文检索向量（应用层写入）
    content_tsv: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)
    created_at:  Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relations
    document:  Mapped["Document"]  = relationship(back_populates="chunks")
    embedding: Mapped[Optional["Embedding"]] = relationship(back_populates="chunk", uselist=False)

    __table_args__ = (
        Index("idx_doc_chunks_doc_id", "doc_id"),
    )


# =============================================
# embeddings（pgvector 768 维，HNSW 索引）
# =============================================

class Embedding(Base):
    __tablename__ = "embeddings"

    id:         Mapped[int] = mapped_column(Integer, primary_key=True)
    chunk_id:   Mapped[int] = mapped_column(ForeignKey("doc_chunks.id", ondelete="CASCADE"), nullable=False, unique=True)
    doc_id:     Mapped[int] = mapped_column(ForeignKey("documents.id",  ondelete="CASCADE"), nullable=False)
    dept_id:    Mapped[int] = mapped_column(Integer, nullable=False)  # 冗余存储，加速权限过滤
    embedding:  Mapped[list] = mapped_column(Vector(768), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)  # 记录 embedding 模型版本
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relations
    chunk: Mapped["DocChunk"] = relationship(back_populates="embedding")

    __table_args__ = (
        Index("idx_embeddings_doc_id",  "doc_id"),
        Index("idx_embeddings_dept_id", "dept_id"),
        # HNSW 向量索引在 migration 中手动创建（SQLAlchemy 不支持自动生成）
    )


# =============================================
# conversations
# =============================================

class Conversation(Base):
    __tablename__ = "conversations"

    id:            Mapped[int]                = mapped_column(Integer, primary_key=True)
    user_id:       Mapped[int]                = mapped_column(ForeignKey("users.id"), nullable=False)
    title:         Mapped[Optional[str]]      = mapped_column(String(255), nullable=True)
    status:        Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=ConversationStatus.active
    )
    message_count: Mapped[int]               = mapped_column(Integer, nullable=False, default=0)
    created_at:    Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at:    Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # relations
    user:     Mapped["User"]          = relationship(back_populates="conversations")
    messages: Mapped[List["Message"]] = relationship(back_populates="conversation")

    __table_args__ = (
        Index("idx_conversations_user_id", "user_id", "status", "updated_at"),
    )


# =============================================
# messages
# =============================================

class Message(Base):
    __tablename__ = "messages"

    id:              Mapped[int]         = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int]         = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role:            Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role", values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    content:         Mapped[str]         = mapped_column(Text, nullable=False)
    # [{"doc_id": 1, "chunk_id": 5, "doc_name": "...", "heading": "..."}]
    sources:         Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    input_tokens:    Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    output_tokens:   Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    latency_ms:      Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    created_at:      Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # relations
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("idx_messages_conversation_id", "conversation_id", "created_at"),
    )


# =============================================
# audit_logs（不可删除，无外键约束）
# =============================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id:            Mapped[int]           = mapped_column(BigInteger, primary_key=True)
    operator_id:   Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # 无外键，用户删除后日志保留
    operator_name: Mapped[str]           = mapped_column(String(100), nullable=False)  # 冗余姓名
    action:        Mapped[str]           = mapped_column(String(100), nullable=False)  # 'user.create' / 'doc.upload'
    resource_type: Mapped[Optional[str]] = mapped_column(String(50),  nullable=True)   # 'user' / 'document'
    resource_id:   Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_value:     Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_value:     Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address:    Mapped[Optional[str]]  = mapped_column(INET, nullable=True)
    result:        Mapped[str]            = mapped_column(String(20), nullable=False, default="success")
    detail:        Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    created_at:    Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_audit_logs_operator_id", "operator_id"),
        Index("idx_audit_logs_action",      "action"),
        Index("idx_audit_logs_created_at",  "created_at"),
        Index("idx_audit_logs_resource",    "resource_type", "resource_id"),
    )


# =============================================
# system_config（KV 配置表）
# =============================================

class SystemConfig(Base):
    __tablename__ = "system_config"

    key:        Mapped[str]           = mapped_column(String(100), primary_key=True)
    value:      Mapped[dict]          = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# =============================================
# tool_calls（工具调用记录）
# =============================================

class ToolCall(Base):
    __tablename__ = "tool_calls"

    id:            Mapped[int]           = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    message_id:    Mapped[Optional[int]] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    user_id:       Mapped[int]           = mapped_column(Integer, nullable=False)
    tool_name:     Mapped[str]           = mapped_column(String(100), nullable=False)
    tool_args:     Mapped[dict]          = mapped_column(JSONB, nullable=False)
    tool_result:   Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    allowed:       Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    deny_reason:   Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms:    Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error:         Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    created_at:    Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_tool_calls_user_id", "user_id"),
        Index("idx_tool_calls_tool_name", "tool_name"),
        Index("idx_tool_calls_created_at", "created_at"),
    )


# =============================================
# it_tickets（IT 工单表 — create_it_ticket 工具使用）
# =============================================

class ItTicket(Base):
    __tablename__ = "it_tickets"

    id:            Mapped[int]           = mapped_column(BigInteger, primary_key=True)
    ticket_no:     Mapped[str]           = mapped_column(String(50), nullable=False, unique=True)
    user_id:       Mapped[int]           = mapped_column(Integer, nullable=False)
    issue_type:    Mapped[str]           = mapped_column(String(100), nullable=False)
    description:   Mapped[str]           = mapped_column(Text, nullable=False)
    status:        Mapped[str]           = mapped_column(String(20), nullable=False, default="open")
    handle_note:   Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    handler_id:    Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str]         = mapped_column(String(255), nullable=False, unique=True)
    created_at:    Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at:    Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_it_tickets_user_id", "user_id"),
        Index("idx_it_tickets_status", "status"),
    )


# =============================================
# reimbursement_rules / limits / requests
# =============================================

class ReimbursementRule(Base):
    """报销标准：与制度文档数值保持一致，供 precheck 精确校验。"""
    __tablename__ = "reimbursement_rules"

    id:         Mapped[int]  = mapped_column(Integer, primary_key=True)
    category:   Mapped[str]  = mapped_column(String(50), nullable=False)
    job_level:  Mapped[str]  = mapped_column(String(20), nullable=False)
    daily_max:  Mapped[int]  = mapped_column(Integer, nullable=False)
    annual_max: Mapped[int]  = mapped_column(Integer, nullable=False)
    doc_ref:    Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("uq_rules_cat_level", "category", "job_level", unique=True),
    )


class ReimbursementLimit(Base):
    """员工年度额度占用。"""
    __tablename__ = "reimbursement_limits"

    id:         Mapped[int]  = mapped_column(Integer, primary_key=True)
    user_id:    Mapped[int]  = mapped_column(ForeignKey("users.id"), nullable=False)
    category:   Mapped[str]  = mapped_column(String(50), nullable=False)
    annual_max: Mapped[int]  = mapped_column(Integer, nullable=False)
    used:       Mapped[int]  = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("uq_limit_user_cat", "user_id", "category", unique=True),
    )


class ReimbursementRequest(Base):
    """报销申请单。status: draft/pending/approved/rejected/cancelled"""
    __tablename__ = "reimbursement_requests"

    id:              Mapped[int]  = mapped_column(BigInteger, primary_key=True)
    request_no:      Mapped[str]  = mapped_column(String(50), nullable=False, unique=True)
    user_id:         Mapped[int]  = mapped_column(ForeignKey("users.id"), nullable=False)
    dept_id:         Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True)
    category:        Mapped[str]  = mapped_column(String(50), nullable=False)
    amount:          Mapped[int]  = mapped_column(Integer, nullable=False)
    days:            Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trip_start:      Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    trip_end:        Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    approval_ref:    Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    precheck_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status:          Mapped[str]  = mapped_column(String(20), nullable=False, default="draft")
    idempotency_key: Mapped[str]  = mapped_column(String(255), nullable=False, unique=True)
    approver_id:     Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approver_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at:      Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at:      Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at:      Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_reimb_user_status", "user_id", "status"),
        Index("idx_reimb_dept_status", "dept_id", "status"),
    )


# =============================================
# agent_traces（节点级追踪）
# =============================================

class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id:              Mapped[int]  = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    user_id:         Mapped[int]  = mapped_column(Integer, nullable=False)
    query:           Mapped[str]  = mapped_column(Text, nullable=False)
    intent:          Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    rewritten_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    steps:           Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    tool_calls:      Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    final_answer:    Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sources:         Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    llm_model:       Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    total_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error:           Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:      Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_agent_traces_user", "user_id", "created_at"),
        Index("idx_agent_traces_conv", "conversation_id"),
    )


# =============================================
# qa_records（问答记录，供知识缺口分析）
# =============================================

class QARecord(Base):
    __tablename__ = "qa_records"

    id:              Mapped[int]  = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_id:         Mapped[int]  = mapped_column(Integer, nullable=False)
    dept_id:         Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    query:           Mapped[str]  = mapped_column(Text, nullable=False)
    intent:          Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    top1_score:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    doc_hit:         Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    answer_preview:  Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback:        Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    feedback_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    latency_ms:      Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_gap:          Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gap_resolved:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at:      Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_qa_user_created", "user_id", "created_at"),
        Index("idx_qa_gap", "is_gap", "gap_resolved"),
    )


# =============================================
# eval_runs（评测结果落库，P1）
# =============================================

class EvalRun(Base):
    __tablename__ = "eval_runs"

    id:               Mapped[int] = mapped_column(BigInteger, primary_key=True)
    started_at:       Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at:      Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_cases:      Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scored_cases:     Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeout_count:    Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    intent_accuracy:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    doc_hit_rate:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recall_at_1:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mrr:              Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    heading_hit_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tool_call_accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    citation_rate:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    permission_pass_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_latency_ms:   Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    skip_generation:  Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tool_dry_run:     Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    case_results:     Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    failed_cases:     Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    operator_id:      Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note:             Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
