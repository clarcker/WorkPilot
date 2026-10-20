"""员工自己的 IT 工单列表。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_active_user
from db.models import ItTicket, User
from db.session import get_db
from schemas.common import BaseResp

router = APIRouter()


@router.get("/mine", response_model=BaseResp[list[dict]])
async def my_tickets(
    status: str | None = Query(None),
    current_user: User = Depends(get_active_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(ItTicket).where(ItTicket.user_id == current_user.id)
    if status:
        q = q.where(ItTicket.status == status)
    rows = (
        await db.execute(q.order_by(ItTicket.created_at.desc()).limit(20))
    ).scalars().all()
    return BaseResp.ok([
        {
            "id": t.id,
            "ticket_no": t.ticket_no,
            "issue_type": t.issue_type,
            "description": t.description,
            "status": t.status,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ])
