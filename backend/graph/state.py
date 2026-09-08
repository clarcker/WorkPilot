"""
LangGraph RAG 工作流状态定义。

所有节点共享同一个 RAGState 对象，节点返回字典更新对应字段。

注意：token_queue 是 asyncio.Queue，不可序列化，仅用于内存内流式传输，
      不启用 LangGraph checkpointing 时不影响使用。
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional
from typing_extensions import TypedDict


class HistoryMessage(TypedDict):
    role:    str   # "user" | "assistant"
    content: str


class RAGState(TypedDict):
    # ── 输入 ──────────────────────────────────────
    query:            str
    user_id:          int
    user_role:        str            # "super_admin" | "dept_admin" | "employee"
    user_dept_id:     Optional[int]
    conversation_history: list[HistoryMessage]  # 最近 N 轮历史（不含当前问题）

    # ── 脱敏节点输出 ───────────────────────────────
    anonymized_query: str

    # ── 意图分类节点输出 ───────────────────────────
    intent: str    # "rag" | "chitchat"

    # ── 检索节点输出 ───────────────────────────────
    retrieved_chunks: list[dict]   # RetrievedChunk TypedDict 列表

    # ── 生成节点输出 ───────────────────────────────
    full_answer: str
    sources:     list[dict]   # 去重后的来源列表

    # ── 错误信息 ───────────────────────────────────
    error: Optional[str]

    # ── 工具调用相关 ─────────────────────────────────
    need_tool:       bool             # 是否需要调用工具
    tool_name:       Optional[str]    # LLM 选择的工具名
    tool_args:       dict             # LLM 生成的工具参数
    tool_result:     Optional[dict]   # 工具执行结果
    permission_denied: Optional[str]  # 权限拒绝原因
    trace:           list[dict]       # 每个节点的执行追踪

    # ── 流式传输队列（in-memory only，不参与 checkpointing）──
    token_queue: Optional[asyncio.Queue]  # asyncio.Queue[dict | None]
