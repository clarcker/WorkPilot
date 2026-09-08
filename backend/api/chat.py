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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_active_user
from db.models import Conversation, ConversationStatus, Message, MessageRole, User
from db.session import async_session_factory, get_db
from graph.state import HistoryMessage, RAGState
from graph.workflow import rag_graph
from schemas.chat import ChatRequest, ConversationDetail, ConversationOut, MessageOut
from schemas.common import BaseResp, PagedData

logger = logging.getLogger(__name__)
router = APIRouter()


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
    if is_new_conv:
        # 新会话：标题取问题前 30 字
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

    # ── 5. 运行 LangGraph RAG 流水线 ─────────────────────────────
    token_queue: asyncio.Queue = asyncio.Queue()

    initial_state = RAGState(
        query=req.query,
        user_id=user_id,
        user_role=user_role,
        user_dept_id=user_dept_id,
        conversation_history=history,
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

    # ── 8. 推送 sources 事件 ──────────────────────────────────────
    if sources:
        yield sse({"type": "sources", "content": sources})

    # ── 9. 保存助手消息，更新会话 ─────────────────────────────────
    assistant_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.assistant,
        content=full_answer,
        sources=sources if sources else None,
    )
    db.add(assistant_msg)
    conv.message_count += 2   # 用户 + 助手各一条

    try:
        await db.commit()
    except Exception as exc:
        logger.error(f"[chat_stream] 保存消息失败: {exc}")
        await db.rollback()

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
