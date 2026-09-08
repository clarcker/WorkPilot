"""create_it_ticket 工具 — 创建 IT 工单（mock + 幂等）。"""
from __future__ import annotations
import time
from sqlalchemy import select
from db.models import ItTicket
from db.session import async_session_factory
from tools.base import ToolContext, ToolResult, make_idempotency_key, tool


@tool(
    name="create_it_ticket",
    description="创建 IT 支持工单。需要问题类型（网络故障/打印机故障/账号问题/软件安装/其他）和问题描述。重复提交返回已有工单。",
    permissions=["employee", "dept_admin", "super_admin"],
    is_idempotent=True,
)
async def create_it_ticket(args: dict, ctx: ToolContext) -> ToolResult:
    issue_type = args.get("issue_type", "")
    description = args.get("description", "")
    if not issue_type.strip():
        return ToolResult(success=False, error="问题类型不能为空")
    if not description.strip():
        return ToolResult(success=False, error="问题描述不能为空")

    idem_key = make_idempotency_key(ctx.user_id, issue_type=issue_type.strip(), description=description.strip())

    async with async_session_factory() as db:
        existing = await db.scalar(select(ItTicket).where(ItTicket.idempotency_key == idem_key))
        if existing:
            return ToolResult(success=True, data={
                "ticket_no": existing.ticket_no, "status": existing.status,
                "message": "该工单已存在（幂等返回）", "created_at": existing.created_at.isoformat()})

        ticket_no = f"IT-{int(time.time())}-{ctx.user_id:04d}"
        ticket = ItTicket(ticket_no=ticket_no, user_id=ctx.user_id, issue_type=issue_type.strip(),
                          description=description.strip(), status="open", idempotency_key=idem_key)
        db.add(ticket)
        await db.commit()
        await db.refresh(ticket)
        return ToolResult(success=True, data={
            "ticket_no": ticket.ticket_no, "status": "open",
            "message": "工单创建成功，IT 部门将尽快处理", "created_at": ticket.created_at.isoformat()})
