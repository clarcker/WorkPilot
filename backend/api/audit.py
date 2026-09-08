"""
审计日志查询路由（只读，仅超级管理员可访问）

GET /api/admin/audit/   — 分页查询，支持按 action、操作人、时间范围过滤
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import require_super_admin
from db.models import AuditLog, User
from db.session import get_db
from schemas.common import BaseResp, PagedData

router = APIRouter()


@router.get("/", response_model=BaseResp)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None),
    operator_name: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    q = select(AuditLog)

    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
    if operator_name:
        q = q.where(AuditLog.operator_name.ilike(f"%{operator_name}%"))
    if result:
        q = q.where(AuditLog.result == result)
    if start_time:
        q = q.where(AuditLog.created_at >= start_time)
    if end_time:
        q = q.where(AuditLog.created_at <= end_time)

    total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0

    q = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    logs = (await db.execute(q)).scalars().all()

    items = [
        {
            "id": log.id,
            "operator_id": log.operator_id,
            "operator_name": log.operator_name,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "ip_address": str(log.ip_address) if log.ip_address else None,
            "result": log.result,
            "detail": log.detail,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]

    return BaseResp.ok(
        data=PagedData(items=items, total=total, page=page, page_size=page_size)
    )
