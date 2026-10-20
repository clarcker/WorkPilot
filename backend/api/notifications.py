"""通知 API：列表 / 已读。管理后台用。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import require_admin
from db.models import Notification, User
from db.session import get_db
from schemas.common import BaseResp, PagedData

router = APIRouter()


@router.get("/notifications", response_model=BaseResp[PagedData[dict]])
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    conds = [Notification.user_id == current_user.id]
    if unread_only:
        conds.append(Notification.is_read == False)  # noqa: E712
    from sqlalchemy import func
    total = await db.scalar(select(func.count(Notification.id)).where(*conds)) or 0
    rows = (
        await db.execute(
            select(Notification)
            .where(*conds)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    unread = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    ) or 0
    return BaseResp.ok(PagedData(
        items=[{
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "level": n.level,
            "source": n.source,
            "payload": n.payload,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        } for n in rows],
        total=total,
        page=page,
        page_size=page_size,
    ))


@router.post("/notifications/{nid}/read", response_model=BaseResp[None])
async def mark_read(
    nid: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(Notification.id == nid, Notification.user_id == current_user.id)
        .values(is_read=True)
    )
    await db.commit()
    return BaseResp.ok(message="ok")


@router.post("/notifications/read-all", response_model=BaseResp[None])
async def mark_all_read(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    await db.commit()
    return BaseResp.ok(message="ok")


@router.get("/notifications/unread-count", response_model=BaseResp[dict])
async def unread_count(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    n = await db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,  # noqa: E712
        )
    ) or 0
    return BaseResp.ok({"count": n})
