"""query_employee_profile — 读 users / departments 表。"""
from __future__ import annotations

from sqlalchemy import select

from db.models import Department, User
from db.session import async_session_factory
from tools.base import ToolContext, ToolResult, tool


@tool(
    name="query_employee_profile",
    description=(
        "查询员工基本信息（姓名、部门、职位/职级、工号、邮箱、入职日期）。"
        "不传 user_id 时查询当前登录用户自己；普通员工只能查自己，"
        "部门管理员和超级管理员可传 user_id 查询他人。"
    ),
    permissions=["employee", "dept_admin", "super_admin"],
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "integer",
                "description": "要查询的员工 user_id；省略则查询当前登录用户自己",
            },
        },
    },
)
async def query_employee_profile(args: dict, ctx: ToolContext) -> ToolResult:
    _uid = args.get("user_id")
    target_user_id = ctx.user_id if _uid in (None, "") else int(_uid)
    if ctx.user_role == "employee" and target_user_id != ctx.user_id:
        return ToolResult(success=False, deny_reason="普通员工只能查询自己的信息")

    async with async_session_factory() as db:
        user = await db.scalar(select(User).where(User.id == target_user_id))
        if not user:
            return ToolResult(success=False, error=f"未找到员工 (user_id={target_user_id})")
        dept_name = None
        if user.dept_id:
            dept = await db.scalar(select(Department).where(Department.id == user.dept_id))
            dept_name = dept.dept_name if dept else None

    return ToolResult(
        success=True,
        data={
            "user_id": user.id,
            "name": user.real_name,
            "display_name": user.display_name,
            "dept": dept_name,
            "job_level": user.job_level,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "employee_no": user.employee_no,
            "email": user.email,
            "status": "在职" if user.is_active else "停用",
        },
    )
