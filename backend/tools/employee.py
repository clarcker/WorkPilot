"""query_employee_profile 工具 — 查询员工基本信息（mock 数据）。"""
from __future__ import annotations
from tools.base import ToolContext, ToolResult, tool

_MOCK_EMPLOYEES = {
    1: {"user_id": 1, "name": "张三", "dept": "技术研发部", "position": "高级工程师",
        "employee_no": "RD001", "email": "zhangsan@company.com", "phone": "13800138001",
        "hire_date": "2023-03-15", "status": "在职"},
    2: {"user_id": 2, "name": "李四", "dept": "人力资源部", "position": "HR 主管",
        "employee_no": "HR001", "email": "lisi@company.com", "phone": "13800138002",
        "hire_date": "2022-08-01", "status": "在职"},
    3: {"user_id": 3, "name": "王五", "dept": "技术研发部", "position": "前端工程师",
        "employee_no": "RD002", "email": "wangwu@company.com", "phone": "13800138003",
        "hire_date": "2024-01-10", "status": "在职"},
    100: {"user_id": 100, "name": "管理员", "dept": "管理层", "position": "系统管理员",
          "employee_no": "ADM001", "email": "admin@company.com", "phone": "13800138100",
          "hire_date": "2020-01-01", "status": "在职"},
}


@tool(
    name="query_employee_profile",
    description=(
        "查询员工基本信息（姓名、部门、职位、工号、邮箱、入职日期）。"
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
    # 不能用 args.get("user_id", ctx.user_id)：LLM 常常显式给出 "user_id": null，
    # 键存在时默认值不生效，会把 None 当成目标用户传下去
    _uid = args.get("user_id")
    target_user_id = ctx.user_id if _uid in (None, "") else _uid
    if ctx.user_role == "employee" and target_user_id != ctx.user_id:
        return ToolResult(success=False, deny_reason="普通员工只能查询自己的信息")
    employee = _MOCK_EMPLOYEES.get(target_user_id)
    if not employee:
        return ToolResult(success=False, error=f"未找到员工 (user_id={target_user_id})")
    return ToolResult(success=True, data=employee)
