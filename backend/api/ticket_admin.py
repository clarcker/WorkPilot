"""IT 工单处理（管理员）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import write_audit
from core.deps import require_admin
from db.models import Department, ItTicket, User, UserRole
from db.session import get_db
from schemas.common import BaseResp, PagedData

router = APIRouter()


def _get_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


class TicketDecision(BaseModel):
    status: str  # open / in_progress / closed
    handle_note: str | None = None


@router.get("/all", response_model=BaseResp[PagedData[dict]])
async def list_all_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """超管全部；部门管理员仅本部门用户提交的工单。"""
    q = select(ItTicket)
    if current_user.role == UserRole.dept_admin:
        dept_users = select(User.id).where(User.dept_id == current_user.dept_id)
        q = q.where(ItTicket.user_id.in_(dept_users))
    if status:
        q = q.where(ItTicket.status == status)

    total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = (
        await db.execute(
            q.order_by(ItTicket.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    # 附带提交人姓名
    user_ids = {t.user_id for t in rows}
    users = {}
    if user_ids:
        urows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users = {u.id: u.real_name for u in urows}

    items = [
        {
            "id": t.id,
            "ticket_no": t.ticket_no,
            "user_id": t.user_id,
            "user_name": users.get(t.user_id, ""),
            "issue_type": t.issue_type,
            "description": t.description,
            "status": t.status,
            "handle_note": t.handle_note,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]
    return BaseResp.ok(PagedData(items=items, total=total, page=page, page_size=page_size))


@router.post("/{ticket_id}/decision", response_model=BaseResp[dict])
async def update_ticket(
    ticket_id: int,
    body: TicketDecision,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.status not in ("open", "in_progress", "closed"):
        raise HTTPException(400, detail={"code": 40010, "message": "非法状态"})

    t = await db.scalar(select(ItTicket).where(ItTicket.id == ticket_id))
    if not t:
        raise HTTPException(404, detail={"code": 40400, "message": "工单不存在"})

    if current_user.role == UserRole.dept_admin:
        owner = await db.scalar(select(User).where(User.id == t.user_id))
        if not owner or owner.dept_id != current_user.dept_id:
            raise HTTPException(403, detail={"code": 40301, "message": "无权处理其他部门工单"})

    old_status = t.status
    t.status = body.status
    t.handle_note = body.handle_note
    t.handler_id = current_user.id

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action="ticket.update",
        resource_type="it_ticket",
        resource_id=t.ticket_no,
        old_value={"status": old_status},
        new_value={"status": body.status, "handle_note": body.handle_note},
        ip_address=_get_ip(request),
    )
    await db.commit()
    return BaseResp.ok({"ticket_no": t.ticket_no, "status": t.status})
