"""query_reimbursement_limit 工具 — 查询员工报销额度（mock 数据）。"""
from __future__ import annotations
from tools.base import ToolContext, ToolResult, tool

_MOCK_LIMITS = {
    1: {"user_id": 1, "name": "张三", "limits": {
        "差旅住宿": {"daily_max": 500, "annual_max": 50000, "used": 12300},
        "交通补贴": {"daily_max": 200, "annual_max": 20000, "used": 5600},
        "餐饮补贴": {"daily_max": 100, "annual_max": 15000, "used": 8200},
        "通讯补贴": {"monthly_max": 300, "annual_max": 3600, "used": 1800}}},
    2: {"user_id": 2, "name": "李四", "limits": {
        "差旅住宿": {"daily_max": 500, "annual_max": 50000, "used": 8900},
        "交通补贴": {"daily_max": 200, "annual_max": 20000, "used": 3200},
        "餐饮补贴": {"daily_max": 100, "annual_max": 15000, "used": 6100},
        "通讯补贴": {"monthly_max": 300, "annual_max": 3600, "used": 1200}}},
    3: {"user_id": 3, "name": "王五", "limits": {
        "差旅住宿": {"daily_max": 400, "annual_max": 40000, "used": 15200},
        "交通补贴": {"daily_max": 150, "annual_max": 15000, "used": 4800},
        "餐饮补贴": {"daily_max": 80, "annual_max": 12000, "used": 7500},
        "通讯补贴": {"monthly_max": 200, "annual_max": 2400, "used": 1000}}},
}


@tool(
    name="query_reimbursement_limit",
    description="查询员工各类报销额度，包括年度上限、已用金额、剩余额度。可指定类别（差旅住宿/交通补贴/餐饮补贴/通讯补贴）。只能查自己的。",
    permissions=["employee", "dept_admin", "super_admin"],
)
async def query_reimbursement_limit(args: dict, ctx: ToolContext) -> ToolResult:
    target_user_id = args.get("user_id", ctx.user_id)
    category = args.get("category")
    if ctx.user_role == "employee" and target_user_id != ctx.user_id:
        return ToolResult(success=False, deny_reason="普通员工只能查询自己的报销额度")
    record = _MOCK_LIMITS.get(target_user_id)
    if not record:
        return ToolResult(success=False, error=f"未找到员工报销记录 (user_id={target_user_id})")
    if category:
        limit_info = record["limits"].get(category)
        if not limit_info:
            return ToolResult(success=False, error=f"未知报销类别: {category}")
        remaining = limit_info["annual_max"] - limit_info["used"]
        return ToolResult(success=True, data={
            "user_id": target_user_id, "name": record["name"],
            "category": category, **limit_info, "remaining": remaining})
    all_limits = {cat: {**info, "remaining": info["annual_max"] - info["used"]}
                  for cat, info in record["limits"].items()}
    return ToolResult(success=True, data={
        "user_id": target_user_id, "name": record["name"], "limits": all_limits})
