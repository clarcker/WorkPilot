"""Agent 节点级 trace 查询。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import require_admin, require_super_admin
from db.models import AgentTrace, User, UserRole
from db.session import get_db
from schemas.common import BaseResp, PagedData

router = APIRouter()


@router.get("/", response_model=BaseResp[PagedData[dict]])
async def list_traces(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: int | None = Query(None),
    conversation_id: int | None = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    超管：全部；部门管理员：仅本部门用户。
    """
    q = select(AgentTrace)
    if current_user.role == UserRole.dept_admin:
        from db.models import User as U
        dept_users = select(U.id).where(U.dept_id == current_user.dept_id)
        q = q.where(AgentTrace.user_id.in_(dept_users))
    if user_id:
        q = q.where(AgentTrace.user_id == user_id)
    if conversation_id:
        q = q.where(AgentTrace.conversation_id == conversation_id)

    total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = (
        await db.execute(
            q.order_by(AgentTrace.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = [
        {
            "id": t.id,
            "conversation_id": t.conversation_id,
            "user_id": t.user_id,
            "query": t.query[:200],
            "intent": t.intent,
            "rewritten_query": t.rewritten_query,
            "steps": t.steps,
            "tool_calls": t.tool_calls,
            "llm_model": t.llm_model,
            "total_latency_ms": t.total_latency_ms,
            "error": t.error,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]
    return BaseResp.ok(PagedData(items=items, total=total, page=page, page_size=page_size))


@router.get("/{trace_id}", response_model=BaseResp[dict])
async def get_trace(
    trace_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    t = await db.scalar(select(AgentTrace).where(AgentTrace.id == trace_id))
    if not t:
        raise HTTPException(404, detail={"code": 40400, "message": "trace 不存在"})
    if current_user.role == UserRole.dept_admin:
        from db.models import User as U
        owner = await db.scalar(select(U).where(U.id == t.user_id))
        if not owner or owner.dept_id != current_user.dept_id:
            raise HTTPException(403, detail={"code": 40301, "message": "无权查看其他部门 trace"})

    return BaseResp.ok({
        "id": t.id,
        "conversation_id": t.conversation_id,
        "user_id": t.user_id,
        "query": t.query,
        "intent": t.intent,
        "rewritten_query": t.rewritten_query,
        "steps": t.steps,
        "tool_calls": t.tool_calls,
        "final_answer": t.final_answer,
        "sources": t.sources,
        "llm_model": t.llm_model,
        "total_latency_ms": t.total_latency_ms,
        "error": t.error,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    })
