"""报销工具：额度查询 / 预审 / 提交 / 进度（DB 化，替代 mock）。"""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select

from db.models import (
    ReimbursementLimit,
    ReimbursementRequest,
    ReimbursementRule,
    User,
)
from db.session import async_session_factory
from tools.base import ToolContext, ToolResult, make_idempotency_key, tool

CATEGORIES = ["差旅住宿", "交通补贴", "餐饮补贴", "通讯补贴"]


async def _load_user(db, user_id: int) -> Optional[User]:
    return await db.scalar(select(User).where(User.id == user_id))


async def _load_limit(db, user_id: int, category: str) -> Optional[ReimbursementLimit]:
    return await db.scalar(
        select(ReimbursementLimit).where(
            ReimbursementLimit.user_id == user_id,
            ReimbursementLimit.category == category,
        )
    )


async def _load_rule(db, category: str, job_level: str) -> Optional[ReimbursementRule]:
    rule = await db.scalar(
        select(ReimbursementRule).where(
            ReimbursementRule.category == category,
            ReimbursementRule.job_level == job_level,
        )
    )
    if rule:
        return rule
    # 回退 mid
    return await db.scalar(
        select(ReimbursementRule).where(
            ReimbursementRule.category == category,
            ReimbursementRule.job_level == "mid",
        )
    )


def _target_uid(args: dict, ctx: ToolContext) -> int:
    _uid = args.get("user_id")
    return ctx.user_id if _uid in (None, "") else int(_uid)


@tool(
    name="query_reimbursement_limit",
    description=(
        "查询员工的报销额度（年度上限、已用金额、剩余额度）。"
        "不传 category 时返回全部类别；不传 user_id 时查询当前登录用户自己。"
        "普通员工只能查自己。"
    ),
    permissions=["employee", "dept_admin", "super_admin"],
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": CATEGORIES,
                "description": "报销类别；省略则返回全部类别",
            },
            "user_id": {
                "type": "integer",
                "description": "要查询的员工 user_id；省略则查询当前登录用户自己",
            },
        },
    },
)
async def query_reimbursement_limit(args: dict, ctx: ToolContext) -> ToolResult:
    target_user_id = _target_uid(args, ctx)
    category = args.get("category")
    if ctx.user_role == "employee" and target_user_id != ctx.user_id:
        # 不透露目标用户是否存在
        return ToolResult(success=False, deny_reason="普通员工只能查询自己的报销额度")

    async with async_session_factory() as db:
        user = await _load_user(db, target_user_id)
        if not user:
            return ToolResult(success=False, error="未找到员工报销记录")
        limits = (
            await db.execute(
                select(ReimbursementLimit).where(
                    ReimbursementLimit.user_id == target_user_id
                )
            )
        ).scalars().all()

    by_cat = {
        r.category: {
            "annual_max": r.annual_max,
            "used": r.used,
            "remaining": r.annual_max - r.used,
        }
        for r in limits
    }
    if category:
        info = by_cat.get(category)
        if not info:
            return ToolResult(success=False, error=f"未知报销类别: {category}")
        return ToolResult(
            success=True,
            data={
                "user_id": target_user_id,
                "name": user.real_name,
                "job_level": user.job_level,
                "category": category,
                **info,
            },
        )
    return ToolResult(
        success=True,
        data={
            "user_id": target_user_id,
            "name": user.real_name,
            "job_level": user.job_level,
            "limits": by_cat,
        },
    )


@tool(
    name="precheck_reimbursement",
    description=(
        "报销智能预审（纯代码计算，不落库）。"
        "根据类别、金额、天数与职级标准比对是否超标、年度额度是否够用。"
        "在提交报销前必须先调用本工具。"
    ),
    permissions=["employee", "dept_admin", "super_admin"],
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": CATEGORIES,
                "description": "报销类别",
            },
            "amount": {"type": "integer", "description": "报销总金额（元）"},
            "days": {"type": "integer", "description": "天数（住宿类必填）"},
        },
        "required": ["category", "amount"],
    },
)
async def precheck_reimbursement(args: dict, ctx: ToolContext) -> ToolResult:
    category = args.get("category") or ""
    amount = args.get("amount")
    days = args.get("days")

    if category not in CATEGORIES:
        return ToolResult(success=False, error=f"未知报销类别: {category}")
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return ToolResult(success=False, error="金额必须为整数（元）")
    if amount <= 0:
        return ToolResult(success=False, error="金额必须大于 0")

    missing: list[str] = []
    if category == "差旅住宿":
        if days in (None, ""):
            missing.append("days")
        else:
            try:
                days = int(days)
            except (TypeError, ValueError):
                return ToolResult(success=False, error="天数必须为整数")
            if days <= 0:
                return ToolResult(success=False, error="天数必须大于 0")
    if missing:
        return ToolResult(
            success=True,
            data={"ok": False, "missing_slots": missing, "message": "请补充天数"},
            missing_slots=missing,
        )

    async with async_session_factory() as db:
        user = await _load_user(db, ctx.user_id)
        if not user:
            return ToolResult(success=False, error="用户不存在")
        rule = await _load_rule(db, category, user.job_level)
        if not rule:
            return ToolResult(success=False, error=f"未配置 {category} 的报销标准")
        limit = await _load_limit(db, ctx.user_id, category)

    remaining = (limit.annual_max - limit.used) if limit else 0
    violations: list[dict] = []

    # 日均超标（仅住宿类）
    if category == "差旅住宿" and days:
        daily_avg = amount / days
        if daily_avg > rule.daily_max:
            over = amount - rule.daily_max * days
            violations.append({
                "rule": "daily_max",
                "actual": round(daily_avg, 2),
                "limit": rule.daily_max,
                "over_amount": over,
                "doc_ref": rule.doc_ref or "差旅报销管理办法",
                "message": (
                    f"住宿日均 {daily_avg:.0f} 元，超出你职级（{user.job_level}）"
                    f"标准 {rule.daily_max} 元/天，超标 {over} 元，需部门负责人特批"
                ),
            })

    if amount > remaining:
        violations.append({
            "rule": "annual_remaining",
            "actual": amount,
            "limit": remaining,
            "doc_ref": rule.doc_ref or "差旅报销管理办法",
            "message": f"年度剩余额度 {remaining} 元，不足以覆盖本次 {amount} 元",
        })

    ok = not any(v["rule"] == "annual_remaining" for v in violations)
    # 日均超标仍可提交（走特批），额度不够则不可
    return ToolResult(
        success=True,
        data={
            "ok": ok,
            "category": category,
            "amount": amount,
            "days": days,
            "job_level": user.job_level,
            "daily_max": rule.daily_max,
            "annual_max": rule.annual_max,
            "remaining": remaining,
            "requires_special_approval": any(v["rule"] == "daily_max" for v in violations),
            "violations": violations,
        },
    )


@tool(
    name="submit_reimbursement_request",
    description=(
        "提交报销申请。必须先完成 precheck_reimbursement。"
        "首次调用会创建待确认草稿（draft），需用户在确认卡点击确认后才进入审批。"
        "同一表单重复提交返回同一单号（幂等）。"
    ),
    permissions=["employee", "dept_admin", "super_admin"],
    is_idempotent=True,
    parameters={
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "amount": {"type": "integer", "description": "总金额（元）"},
            "days": {"type": "integer", "description": "天数（住宿类）"},
            "trip_start": {"type": "string", "description": "出差开始日期 YYYY-MM-DD"},
            "trip_end": {"type": "string", "description": "出差结束日期 YYYY-MM-DD"},
            "approval_ref": {"type": "string", "description": "关联出差审批单号，可选"},
        },
        "required": ["category", "amount"],
    },
)
async def submit_reimbursement_request(args: dict, ctx: ToolContext) -> ToolResult:
    category = args.get("category") or ""
    if category not in CATEGORIES:
        return ToolResult(success=False, error=f"未知报销类别: {category}")
    try:
        amount = int(args.get("amount"))
    except (TypeError, ValueError):
        return ToolResult(success=False, error="金额必须为整数")

    days = args.get("days")
    if days not in (None, ""):
        try:
            days = int(days)
        except (TypeError, ValueError):
            return ToolResult(success=False, error="天数必须为整数")
    else:
        days = None

    trip_start = (args.get("trip_start") or "").strip() or None
    trip_end = (args.get("trip_end") or "").strip() or None
    approval_ref = (args.get("approval_ref") or "").strip() or None

    missing: list[str] = []
    if category == "差旅住宿" and not days:
        missing.append("days")
    if category == "差旅住宿" and not trip_start:
        missing.append("trip_start")
    if missing:
        return ToolResult(
            success=True,
            data={"ok": False, "missing_slots": missing, "message": "请补充：" + "、".join(missing)},
            missing_slots=missing,
        )

    # 先跑一遍 precheck，失败（额度不够）则拒绝提交
    pre = await precheck_reimbursement(
        {"category": category, "amount": amount, "days": days}, ctx
    )
    if not pre.success:
        return pre
    if pre.data and pre.data.get("missing_slots"):
        return pre
    if pre.data and not pre.data.get("ok"):
        return ToolResult(
            success=False,
            error="预审未通过：" + "；".join(
                v.get("message", "") for v in (pre.data.get("violations") or [])
            ),
            data=pre.data,
        )

    idem_key = make_idempotency_key(
        ctx.user_id,
        category=category,
        amount=amount,
        days=days or 0,
        trip_start=trip_start or "",
        trip_end=trip_end or "",
        approval_ref=approval_ref or "",
    )

    if ctx.dry_run:
        return ToolResult(
            success=True,
            data={
                "request_no": f"RB-DRYRUN-{idem_key[:8]}",
                "status": "dry_run",
                "requires_confirmation": False,
                "message": "演练模式：申请未真正创建",
                "precheck": pre.data,
            },
        )

    async with async_session_factory() as db:
        user = await _load_user(db, ctx.user_id)
        if not user:
            return ToolResult(success=False, error="用户不存在")

        existing = await db.scalar(
            select(ReimbursementRequest).where(
                ReimbursementRequest.idempotency_key == idem_key
            )
        )
        if existing:
            return ToolResult(
                success=True,
                data={
                    "request_id": existing.id,
                    "request_no": existing.request_no,
                    "status": existing.status,
                    "requires_confirmation": existing.status == "draft",
                    "message": "该申请单已存在（幂等返回）",
                    "precheck": existing.precheck_result,
                },
                requires_confirmation=existing.status == "draft",
            )

        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        seq = (await db.scalar(
            select(ReimbursementRequest).where(
                ReimbursementRequest.request_no.like(f"RB-{today}-%")
            ).order_by(ReimbursementRequest.id.desc()).limit(1)
        ))
        n = 1
        if seq:
            try:
                n = int(seq.request_no.rsplit("-", 1)[-1]) + 1
            except ValueError:
                n = 1
        request_no = f"RB-{today}-{n:04d}"

        row = ReimbursementRequest(
            request_no=request_no,
            user_id=ctx.user_id,
            dept_id=user.dept_id,
            category=category,
            amount=amount,
            days=days,
            trip_start=trip_start,
            trip_end=trip_end,
            approval_ref=approval_ref,
            precheck_result=pre.data,
            status="draft",
            idempotency_key=idem_key,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

    return ToolResult(
        success=True,
        requires_confirmation=True,
        data={
            "request_id": row.id,
            "request_no": row.request_no,
            "status": "draft",
            "requires_confirmation": True,
            "message": "申请单已生成，请确认提交",
            "precheck": pre.data,
            "form": {
                "category": category,
                "amount": amount,
                "days": days,
                "trip_start": trip_start,
                "trip_end": trip_end,
                "approval_ref": approval_ref,
            },
        },
    )


@tool(
    name="query_my_reimbursements",
    description=(
        "查询我的报销申请进度。可按状态过滤：draft/pending/approved/rejected。"
        "不传 status 返回最近若干条。"
    ),
    permissions=["employee", "dept_admin", "super_admin"],
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["draft", "pending", "approved", "rejected", "cancelled"],
                "description": "按状态过滤，可选",
            },
        },
    },
)
async def query_my_reimbursements(args: dict, ctx: ToolContext) -> ToolResult:
    status = args.get("status")
    async with async_session_factory() as db:
        q = select(ReimbursementRequest).where(
            ReimbursementRequest.user_id == ctx.user_id
        )
        if status:
            q = q.where(ReimbursementRequest.status == status)
        rows = (
            await db.execute(
                q.order_by(ReimbursementRequest.created_at.desc()).limit(10)
            )
        ).scalars().all()

    items = [
        {
            "request_no": r.request_no,
            "category": r.category,
            "amount": r.amount,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "approver_comment": r.approver_comment,
        }
        for r in rows
    ]
    return ToolResult(success=True, data={"count": len(items), "items": items})
