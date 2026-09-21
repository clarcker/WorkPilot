"""
聊天路由。

POST /api/chat/stream                SSE 流式问答（核心接口）
GET  /api/chat/conversations         列出当前用户会话（分页）
GET  /api/chat/conversations/{id}    获取会话详情（含消息列表）
DELETE /api/chat/conversations/{id}  删除会话

SSE 事件格式（与 CLAUDE.md 一致）：
    data: {"type": "conversation_id", "content": "123"}  ← 新建会话时第一条
    data: {"type": "token",           "content": "..."}
    data: {"type": "sources",         "content": [...]}
    data: {"type": "done",            "content": ""}
    data: {"type": "error",           "content": "错误信息"}
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_active_user
from core.logger import logger as app_logger
from db.models import Conversation, ConversationStatus, Message, MessageRole, SystemConfig, User
from db.session import async_session_factory, get_db
from graph.state import HistoryMessage, RAGState
from graph.workflow import rag_graph
from schemas.chat import ChatRequest, ConversationDetail, ConversationOut, ConversationRename, MessageOut
from schemas.common import BaseResp, PagedData

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_int_config(db: AsyncSession, key: str, default: int) -> int:
    """从 system_config 读整数配置，缺失/类型异常时回退默认值。"""
    raw = await db.scalar(select(SystemConfig.value).where(SystemConfig.key == key))
    if raw is None:
        return default
    if isinstance(raw, dict) and "value" in raw:
        raw = raw["value"]
    try:
        val = int(raw)
        return val if val > 0 else default
    except (TypeError, ValueError):
        return default


async def _enforce_session_limit(db: AsyncSession, user_id: int, max_sessions: int) -> int:
    """超出会话上限时，把最旧的 active 会话归档。返回归档数量。"""
    total = await db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.status == ConversationStatus.active,
        )
    )
    total = total or 0
    if total < max_sessions:
        return 0

    overflow = total - max_sessions + 1  # 给即将新建的会话腾一个位置
    oldest = await db.execute(
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.status == ConversationStatus.active,
        )
        .order_by(Conversation.updated_at.asc(), Conversation.id.asc())
        .limit(overflow)
    )
    rows = oldest.scalars().all()
    for conv in rows:
        conv.status = ConversationStatus.archived
    app_logger.info(
        "[chat] 会话上限触发归档 | user_id={user} archived={n} max={mx}",
        user=user_id, n=len(rows), mx=max_sessions,
    )
    return len(rows)


async def _enforce_message_limit(db: AsyncSession, conv: Conversation, max_messages: int) -> int:
    """超出单会话消息上限时，物理删除最早的消息。返回删除数量。"""
    if conv.message_count < max_messages:
        return 0

    # 当前消息尚未计入 message_count，先为「用户+助手」两条预留空间
    overflow = conv.message_count - max_messages + 2
    oldest = await db.execute(
        select(Message.id)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(overflow)
    )
    ids = [row[0] for row in oldest.all()]
    if not ids:
        return 0

    await db.execute(delete(Message).where(Message.id.in_(ids)))
    conv.message_count = max(0, conv.message_count - len(ids))
    app_logger.info(
        "[chat] 消息上限触发截断 | conv_id={conv} deleted={n} max={mx}",
        conv=conv.id, n=len(ids), mx=max_messages,
    )
    return len(ids)


# ══════════════════════════════════════════════════════════════════
#  POST /stream   核心 SSE 接口
# ══════════════════════════════════════════════════════════════════

@router.post("/stream")
async def chat_stream(
    req:          ChatRequest,
    current_user: User = Depends(get_active_user),
):
    """
    流式问答。返回 text/event-stream。
    由于 StreamingResponse 需要独立管理 DB 生命周期，
    此处不注入 Depends(get_db)，在生成器内部自行开启 session。
    """
    # 捕获当前用户信息（session 关闭后对象可能失效）
    user_id      = current_user.id
    user_role    = current_user.role.value
    user_dept_id = current_user.dept_id

    return StreamingResponse(
        _rag_event_stream(req, user_id, user_role, user_dept_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 告知 Nginx 关闭缓冲
        },
    )


async def _rag_event_stream(
    req:          ChatRequest,
    user_id:      int,
    user_role:    str,
    user_dept_id: int | None,
) -> AsyncIterator[str]:
    """RAG 流式事件生成器。"""

    async with async_session_factory() as db:
        try:
            async for chunk in _rag_gen(db, req, user_id, user_role, user_dept_id):
                yield chunk
        except Exception as exc:
            logger.error(f"[chat_stream] 未捕获异常: {exc}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': '服务内部错误'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'content': ''}, ensure_ascii=False)}\n\n"


async def _rag_gen(
    db:           AsyncSession,
    req:          ChatRequest,
    user_id:      int,
    user_role:    str,
    user_dept_id: int | None,
) -> AsyncIterator[str]:

    def sse(event: dict) -> str:
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    # ── 1. 创建或加载会话 ────────────────────────────────────────
    is_new_conv = req.conversation_id is None
    max_sessions = await _get_int_config(db, "max_sessions_per_user", 200)
    max_messages = await _get_int_config(db, "max_messages_per_session", 500)

    if is_new_conv:
        # 新会话：标题取问题前 30 字；先按上限归档最旧会话
        await _enforce_session_limit(db, user_id, max_sessions)
        title = req.query[:30].strip()
        conv  = Conversation(user_id=user_id, title=title, status=ConversationStatus.active)
        db.add(conv)
        await db.flush()
    else:
        conv = await db.scalar(
            select(Conversation).where(
                Conversation.id == req.conversation_id,
                Conversation.user_id == user_id,
                Conversation.status == ConversationStatus.active,
            )
        )
        if not conv:
            yield sse({"type": "error", "content": "会话不存在或无权访问"})
            yield sse({"type": "done",  "content": ""})
            return

    # ── 2. 若新会话，先推送 conversation_id ──────────────────────
    if is_new_conv:
        yield sse({"type": "conversation_id", "content": str(conv.id)})

    # ── 2b. 会话消息上限：截断最早消息 ───────────────────────────
    await _enforce_message_limit(db, conv, max_messages)

    # ── 3. 保存用户消息 ───────────────────────────────────────────
    user_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.user,
        content=req.query,
    )
    db.add(user_msg)
    await db.flush()

    # ── 4. 加载最近历史（最多 6 条 = 3 轮）───────────────────────
    hist_rows = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conv.id,
            Message.id != user_msg.id,
        )
        .order_by(Message.created_at.desc())
        .limit(6)
    )
    history: list[HistoryMessage] = [
        HistoryMessage(role=m.role.value, content=m.content)
        for m in reversed(hist_rows.scalars().all())
    ]

    # ── 4b. 本会话已执行工具（Q2 多轮工具决策）────────────────────
    from db.models import ToolCall
    session_tool_calls: list[dict] = []
    if not is_new_conv:
        tc_rows = await db.execute(
            select(ToolCall)
            .where(ToolCall.conversation_id == conv.id)
            .order_by(ToolCall.created_at.desc(), ToolCall.id.desc())
            .limit(8)
        )
        session_tool_calls = [
            {
                "tool_name": r.tool_name,
                "tool_args": r.tool_args or {},
                "tool_result": r.tool_result,
                "success": bool(r.allowed and not r.error),
                "error": r.error or r.deny_reason,
            }
            for r in reversed(tc_rows.scalars().all())
        ]

    # ── 5. 运行 LangGraph RAG 流水线 ─────────────────────────────
    token_queue: asyncio.Queue = asyncio.Queue()

    initial_state = RAGState(
        query=req.query,
        user_id=user_id,
        user_role=user_role,
        user_dept_id=user_dept_id,
        conversation_history=history,
        conversation_id=conv.id,
        anonymized_query="",
        intent="",
        retrieved_chunks=[],
        full_answer="",
        sources=[],
        error=None,
        token_queue=token_queue,
        need_tool=False,
        tool_name=None,
        tool_args={},
        tool_result=None,
        permission_denied=None,
        trace=[],
        tool_step=0,
        tool_history=[],
        session_tool_calls=session_tool_calls,
        max_tool_steps=4,
        node_steps=[],
        requires_confirmation=False,
        confirm_payload=None,
        missing_slots=None,
        rewritten_query=None,
    )

    pipeline_task = asyncio.create_task(rag_graph.ainvoke(initial_state))

    # ── 6. 将 token 流转发给 SSE 客户端 ──────────────────────────
    # 流式架构：Ollama → Backend (httpx stream) → Frontend (SSE)
    # 不设单 token 超时，连接会一直保持直到流结束
    try:
        while True:
            event = await token_queue.get()

            if event is None:   # 流结束哨兵（流水线完成后放入）
                break

            yield sse(event)

            if event.get("type") == "error":
                pipeline_task.cancel()
                break

    except asyncio.CancelledError:
        pipeline_task.cancel()
        return

    # ── 7. 等待流水线完成，取最终结果 ────────────────────────────
    try:
        final_state = await asyncio.wait_for(pipeline_task, timeout=10.0)
    except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as exc:
        logger.error(f"[chat_stream] 等待流水线结束失败: {exc}")
        yield sse({"type": "done", "content": ""})
        await db.rollback()
        return

    full_answer = final_state.get("full_answer", "")
    sources     = final_state.get("sources", [])

    # ── 9b. 记录工具调用审计日志 ────────────────────────────────
    tool_name = final_state.get("tool_name")
    if tool_name:
        from core.audit import write_audit, AuditAction
        permission_denied = final_state.get("permission_denied")
        await write_audit(
            db,
            operator_id=user_id,
            operator_name="",
            action=AuditAction.TOOL_DENY if permission_denied else AuditAction.TOOL_CALL,
            resource_type="tool",
            resource_id=tool_name,
            new_value={
                "tool_args": final_state.get("tool_args", {}),
                "allowed": permission_denied is None,
                "deny_reason": permission_denied,
                "result": final_state.get("tool_result"),
            },
            result="denied" if permission_denied else "success",
        )

    # ── 8. sources 已在检索节点提前推送，此处不重复推送 ──────────
    # （final_state.sources 仍会写入 DB，供历史会话回放）

    # ── 9. 保存助手消息，更新会话 ─────────────────────────────────
    assistant_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.assistant,
        content=full_answer,
        sources=sources if sources else None,
    )
    db.add(assistant_msg)
    conv.message_count += 2   # 用户 + 助手各一条

    # ── 9c. 节点级 trace + QA 记录 ───────────────────────────────
    from core.config import settings as app_settings
    from db.models import AgentTrace, QARecord

    steps = final_state.get("node_steps") or []
    tool_hist = final_state.get("tool_history") or []
    top1 = None
    chunks = final_state.get("retrieved_chunks") or []
    if chunks:
        top1 = float(chunks[0].get("score") or 0)
    llm_model = (
        app_settings.openai_model
        if app_settings.llm_provider == "openai_compatible"
        else app_settings.ollama_chat_model
    )
    db.add(AgentTrace(
        conversation_id=conv.id,
        user_id=user_id,
        query=req.query,
        intent=final_state.get("intent"),
        rewritten_query=final_state.get("rewritten_query"),
        steps=steps,
        tool_calls=tool_hist or None,
        final_answer=(full_answer or "")[:4000],
        sources=sources or None,
        llm_model=llm_model,
        error=final_state.get("error"),
    ))
    is_gap = (
        final_state.get("intent") == "rag"
        and (
            not chunks
            or (top1 is not None and top1 < 0.35)
            or "未找到" in (full_answer or "")
            or "没有相关" in (full_answer or "")
        )
    )
    qa_rec = QARecord(
        conversation_id=conv.id,
        user_id=user_id,
        dept_id=user_dept_id,
        query=req.query,
        intent=final_state.get("intent"),
        top1_score=top1,
        doc_hit=bool(chunks),
        answer_preview=(full_answer or "")[:500],
        is_gap=is_gap,
    )
    db.add(qa_rec)

    try:
        await db.commit()
        await db.refresh(qa_rec)
        qa_id = qa_rec.id
    except Exception as exc:
        logger.error(f"[chat_stream] 保存消息失败: {exc}")
        await db.rollback()
        qa_id = None

    # 供前端 👍/👎 反馈
    if qa_id:
        yield sse({"type": "qa_id", "content": qa_id})

    yield sse({"type": "done", "content": ""})

    # ── 10. 通知 generate_answer_node 可以退出（放 None 哨兵）────
    # （正常情况下流水线已完成，queue 里不需要额外操作；
    #  此处为防止 generate_answer_node 卡在 put 调用而做的保险处理）
    try:
        token_queue.put_nowait(None)
    except asyncio.QueueFull:
        pass


# ══════════════════════════════════════════════════════════════════
#  GET /conversations
# ══════════════════════════════════════════════════════════════════

@router.get("/conversations", response_model=BaseResp[PagedData[ConversationOut]])
async def list_conversations(
    page:      int = Query(default=1,  ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_active_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    base = (
        select(Conversation)
        .where(
            Conversation.user_id == current_user.id,
            Conversation.status  == ConversationStatus.active,
        )
    )

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )

    rows = await db.execute(
        base.order_by(Conversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    convs = rows.scalars().all()

    return BaseResp.ok(PagedData(
        items=[ConversationOut.model_validate(c) for c in convs],
        total=total or 0,
        page=page,
        page_size=page_size,
    ))


# ══════════════════════════════════════════════════════════════════
#  GET /conversations/{id}
# ══════════════════════════════════════════════════════════════════

@router.get("/conversations/{conv_id}", response_model=BaseResp[ConversationDetail])
async def get_conversation(
    conv_id: int,
    current_user: User = Depends(get_active_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id      == conv_id,
            Conversation.user_id == current_user.id,
        )
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 40400, "message": "会话不存在"},
        )

    rows = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
    )
    messages = rows.scalars().all()

    return BaseResp.ok(ConversationDetail(
        conversation=ConversationOut.model_validate(conv),
        messages=[MessageOut.model_validate(m) for m in messages],
    ))


# ══════════════════════════════════════════════════════════════════
#  PATCH /conversations/{id}/title   重命名会话
# ══════════════════════════════════════════════════════════════════

@router.patch("/conversations/{conv_id}/title", response_model=BaseResp[ConversationOut])
async def rename_conversation(
    conv_id: int,
    body: ConversationRename,
    current_user: User = Depends(get_active_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id      == conv_id,
            Conversation.user_id == current_user.id,
        )
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 40400, "message": "会话不存在"},
        )
    conv.title = body.title
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(conv)
    return BaseResp.ok(ConversationOut.model_validate(conv))


# ══════════════════════════════════════════════════════════════════
#  DELETE /conversations/{id}
# ══════════════════════════════════════════════════════════════════

@router.delete("/conversations/{conv_id}", response_model=BaseResp[None])
async def delete_conversation(
    conv_id: int,
    current_user: User = Depends(get_active_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id      == conv_id,
            Conversation.user_id == current_user.id,
        )
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 40400, "message": "会话不存在"},
        )

    # 软删除：标记为归档
    conv.status = ConversationStatus.archived
    return BaseResp.ok(message="会话已删除")
