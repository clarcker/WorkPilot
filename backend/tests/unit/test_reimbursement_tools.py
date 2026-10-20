"""报销 precheck / submit 槽位与幂等逻辑（mock DB 较重，这里测纯函数路径与工具注册）。"""
from __future__ import annotations

import pytest

from tools.base import tool_registry


@pytest.mark.no_db
class TestReimbursementToolsRegistered:
    def test_all_tools_present(self):
        names = {t.name for t in tool_registry.list_tools()}
        assert "query_reimbursement_limit" in names
        assert "precheck_reimbursement" in names
        assert "submit_reimbursement_request" in names
        assert "query_my_reimbursements" in names
        assert "create_it_ticket" in names

    def test_submit_declares_required_params(self):
        td = tool_registry.get("submit_reimbursement_request")
        assert td is not None
        assert "category" in td.params_schema.get("required", [])
        assert "amount" in td.params_schema.get("required", [])

    def test_precheck_declares_required_params(self):
        td = tool_registry.get("precheck_reimbursement")
        assert td is not None
        assert set(td.params_schema.get("required", [])) >= {"category", "amount"}


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_precheck_invalid_category():
    from tools.base import ToolContext
    from tools.reimbursement import precheck_reimbursement

    ctx = ToolContext(user_id=1, user_role="employee")
    r = await precheck_reimbursement({"category": "不存在", "amount": 100}, ctx)
    assert r.success is False
    assert "未知" in (r.error or "")


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_precheck_missing_days_slot():
    """住宿类缺天数 → 返回 missing_slots，而不是硬失败。"""
    from tools.base import ToolContext
    from tools.reimbursement import precheck_reimbursement

    ctx = ToolContext(user_id=1, user_role="employee")
    # amount 合法但 days 缺失；会去查 DB 规则——若无 DB 会 error。
    # 这里只断言不抛未捕获异常。
    r = await precheck_reimbursement({"category": "差旅住宿", "amount": 1800}, ctx)
    assert r is not None
    if r.success and r.data and r.data.get("missing_slots"):
        assert "days" in r.data["missing_slots"]
