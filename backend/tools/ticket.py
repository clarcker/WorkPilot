"""create_it_ticket / query_my_tickets 工具。"""
from __future__ import annotations
import time
from sqlalchemy import select
from db.models import ItTicket
from db.session import async_session_factory
from tools.base import ToolContext, ToolResult, make_idempotency_key, tool


@tool(
    name="create_it_ticket",
    description=(
        "为当前用户创建 IT 支持工单。仅在用户明确要求报修/报障/提交工单时调用；"
        "只是询问维修流程或制度规定时不要调用。重复提交返回已有工单。"
    ),
    permissions=["employee", "dept_admin", "super_admin"],
    is_idempotent=True,
    parameters={
        "type": "object",
        "properties": {
            "issue_type": {
                "type": "string",
                "enum": ["网络故障", "打印机故障", "账号问题", "软件安装", "其他"],
                "description": "问题类型",
            },
            "description": {
                "type": "string",
                "description": "问题的具体描述",
            },
        },
        "required": ["issue_type", "description"],
    },
)
async def create_it_ticket(args: dict, ctx: ToolContext) -> ToolResult:
    issue_type = args.get("issue_type", "")
    description = args.get("description", "")
    if not issue_type.strip():
        return ToolResult(success=False, error="问题类型不能为空")
    if not description.strip():
        return ToolResult(success=False, error="问题描述不能为空")

    idem_key = make_idempotency_key(ctx.user_id, issue_type=issue_type.strip(), description=description.strip())

    if ctx.dry_run:
        # 演练模式（评测回归）：参数已校验通过，但不落库
        return ToolResult(success=True, data={
            "ticket_no": f"IT-DRYRUN-{idem_key[:8]}", "status": "dry_run",
            "message": "演练模式：工单未真正创建", "created_at": None})

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


@tool(
    name="query_my_tickets",
    description=(
        "查询当前用户自己的 IT 工单进度。"
        "用户问「我上次报的打印机修好了吗 / 工单处理得怎么样了」时调用。"
        "可按状态过滤：open/in_progress/closed。"
    ),
    permissions=["employee", "dept_admin", "super_admin"],
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["open", "in_progress", "closed"],
                "description": "按状态过滤，可选",
            },
        },
    },
)
async def query_my_tickets(args: dict, ctx: ToolContext) -> ToolResult:
    status = args.get("status")
    async with async_session_factory() as db:
        q = select(ItTicket).where(ItTicket.user_id == ctx.user_id)
        if status:
            q = q.where(ItTicket.status == status)
        rows = (
            await db.execute(q.order_by(ItTicket.created_at.desc()).limit(10))
        ).scalars().all()

    items = [
        {
            "ticket_no": t.ticket_no,
            "issue_type": t.issue_type,
            "description": t.description,
            "status": t.status,
            "handle_note": t.handle_note,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]
    return ToolResult(success=True, data={"count": len(items), "items": items})