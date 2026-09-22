"""报销申请：确认 / 取消 / 我的列表 / 部门审批队列。

状态机写路径全部 `with_for_update` 锁申请单（与额度行），避免双击 confirm
双扣额度、双管理员 reject 双退额度。
"""
from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import AuditAction, write_audit
from core.deps import get_active_user, require_admin
from db.models import (
    ReimbursementLimit,
    ReimbursementRequest,
    User,
    UserRole,
)
from db.session import get_db
from schemas.common import BaseResp, PagedData
from pydantic import BaseModel

router = APIRouter()


class DecisionBody(BaseModel):
    approved: bool
    comment: str | None = None


def _get_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _lock_request(
    db: AsyncSession,
    request_id: int,
    user_id: int | None = None,
) -> ReimbursementRequest:
    """SELECT ... FOR UPDATE 锁定申请单行。"""
    q = select(ReimbursementRequest).where(
        ReimbursementRequest.id == request_id
    ).with_for_update()
    if user_id is not None:
        q = q.where(ReimbursementRequest.user_id == user_id)
    row = await db.scalar(q)
    if not row:
        raise HTTPException(404, detail={"code": 40400, "message": "申请单不存在"})
    return row


async def _lock_limit(
    db: AsyncSession,
    user_id: int,
    category: str,
) -> ReimbursementLimit | None:
    return await db.scalar(
        select(ReimbursementLimit)
        .where(
            ReimbursementLimit.user_id == user_id,
            ReimbursementLimit.category == category,
        )
        .with_for_update()
    )


@router.post("/{request_id}/confirm", response_model=BaseResp[dict])
async def confirm_request(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_active_user),
    db: AsyncSession = Depends(get_db),
):
    """用户确认草稿 → 进入待审批，并占用年度额度。并发双击只扣一次。"""
    row = await _lock_request(db, request_id, current_user.id)
    if row.status != "draft":
        return BaseResp.ok({
            "request_no": row.request_no,
            "status": row.status,
            "message": f"当前状态为 {row.status}，无需重复确认",
        })

    limit = await _lock_limit(db, current_user.id, row.category)
    if limit:
        if limit.used + row.amount > limit.annual_max:
            raise HTTPException(
                400,
                detail={"code": 40010, "message": "年度剩余额度不足，无法提交"},
            )
        limit.used += row.amount

    row.status = "pending"
    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action="reimbursement.confirm",
        resource_type="reimbursement",
        resource_id=row.request_no,
        new_value={"amount": row.amount, "category": row.category},
        ip_address=_get_ip(request),
    )
    await db.commit()
    return BaseResp.ok({
        "request_no": row.request_no,
        "status": "pending",
        "message": "已提交，等待部门审批",
    })


@router.post("/{request_id}/cancel", response_model=BaseResp[dict])
async def cancel_request(
    request_id: int,
    request: Request,
    current_user: User = Depends(get_active_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _lock_request(db, request_id, current_user.id)
    if row.status not in ("draft", "pending"):
        raise HTTPException(400, detail={"code": 40010, "message": f"状态 {row.status} 不可取消"})

    if row.status == "pending":
        limit = await _lock_limit(db, current_user.id, row.category)
        if limit:
            limit.used = max(0, limit.used - row.amount)

    row.status = "cancelled"
    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action="reimbursement.cancel",
        resource_type="reimbursement",
        resource_id=row.request_no,
        ip_address=_get_ip(request),
    )
    await db.commit()
    return BaseResp.ok({"request_no": row.request_no, "status": "cancelled", "message": "已取消"})


@router.get("/mine", response_model=BaseResp[list[dict]])
async def my_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: User = Depends(get_active_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(ReimbursementRequest).where(
        ReimbursementRequest.user_id == current_user.id
    )
    if status_filter:
        q = q.where(ReimbursementRequest.status == status_filter)
    rows = (
        await db.execute(q.order_by(ReimbursementRequest.created_at.desc()).limit(20))
    ).scalars().all()
    return BaseResp.ok([
        {
            "id": r.id,
            "request_no": r.request_no,
            "category": r.category,
            "amount": r.amount,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "approver_comment": r.approver_comment,
        }
        for r in rows
    ])


@router.get("/approvals", response_model=BaseResp[PagedData[dict]])
async def approval_queue(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """部门审批队列：超管看全部，部门管理员只看本部门。"""
    q = select(ReimbursementRequest).where(
        ReimbursementRequest.status == "pending"
    )
    if current_user.role == UserRole.dept_admin:
        q = q.where(ReimbursementRequest.dept_id == current_user.dept_id)

    total = await db.scalar(
        select(func.count()).select_from(q.subquery())
    )
    rows = (
        await db.execute(
            q.order_by(ReimbursementRequest.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = [
        {
            "id": r.id,
            "request_no": r.request_no,
            "user_id": r.user_id,
            "dept_id": r.dept_id,
            "category": r.category,
            "amount": r.amount,
            "days": r.days,
            "trip_start": r.trip_start,
            "trip_end": r.trip_end,
            "approval_ref": r.approval_ref,
            "precheck_result": r.precheck_result,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return BaseResp.ok(PagedData(items=items, total=total or 0, page=page, page_size=page_size))


@router.post("/{request_id}/decision", response_model=BaseResp[dict])
async def decide_request(
    request_id: int,
    body: DecisionBody,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await _lock_request(db, request_id)
    if current_user.role == UserRole.dept_admin and row.dept_id != current_user.dept_id:
        raise HTTPException(403, detail={"code": 40301, "message": "无权审批其他部门的申请"})
    if row.status != "pending":
        raise HTTPException(400, detail={"code": 40010, "message": f"状态 {row.status} 不可审批"})

    row.status = "approved" if body.approved else "rejected"
    row.approver_id = current_user.id
    row.approver_comment = body.comment
    row.decided_at = datetime.datetime.now(datetime.timezone.utc)

    if not body.approved:
        limit = await _lock_limit(db, row.user_id, row.category)
        if limit:
            limit.used = max(0, limit.used - row.amount)

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action="reimbursement.approve" if body.approved else "reimbursement.reject",
        resource_type="reimbursement",
        resource_id=row.request_no,
        new_value={"comment": body.comment},
        ip_address=_get_ip(request),
    )
    await db.commit()
    return BaseResp.ok({"request_no": row.request_no, "status": row.status})
