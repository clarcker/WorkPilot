"""工具调用工作流集成测试。

这些测试验证 LangGraph 工作流的工具调用路径。
使用 mock LLM 和 embedding 服务。
"""
import pytest
from unittest.mock import AsyncMock, patch

from graph.state import RAGState
from tools.base import ToolContext, ToolResult, tool_registry


def _make_state(query: str, intent: str = "rag", user_role: str = "employee",
                user_id: int = 1, user_dept_id: int = 1) -> RAGState:
    """创建测试用 RAGState。"""
    return RAGState(
        query=query,
        user_id=user_id,
        user_role=user_role,
        user_dept_id=user_dept_id,
        conversation_history=[],
        anonymized_query=query,
        intent=intent,
        retrieved_chunks=[],
        full_answer="",
        sources=[],
        error=None,
        token_queue=None,
        need_tool=False,
        tool_name=None,
        tool_args={},
        tool_result=None,
        permission_denied=None,
        trace=[],
    )


@pytest.mark.no_db
class TestToolRegistryIntegration:
    """测试工具注册和调用。"""

    def test_all_tools_registered(self):
        """三个工具都已注册。"""
        import tools.employee  # noqa: F401
        import tools.reimbursement  # noqa: F401
        import tools.ticket  # noqa: F401
        assert tool_registry.get("query_employee_profile") is not None
        assert tool_registry.get("query_reimbursement_limit") is not None
        assert tool_registry.get("create_it_ticket") is not None

    @pytest.mark.asyncio
    async def test_employee_profile_query_self(self):
        """员工可以查自己的信息。"""
        import tools.employee  # noqa: F401
        ctx = ToolContext(user_id=1, user_role="employee")
        result = await tool_registry.execute("query_employee_profile", {"user_id": 1}, ctx)
        assert result.success is True
        assert result.data["name"] == "张三"

    @pytest.mark.asyncio
    async def test_employee_profile_query_others_denied(self):
        """员工不能查别人的信息。"""
        import tools.employee  # noqa: F401
        ctx = ToolContext(user_id=1, user_role="employee")
        result = await tool_registry.execute("query_employee_profile", {"user_id": 2}, ctx)
        assert result.success is False
        assert result.deny_reason is not None

    @pytest.mark.asyncio
    async def test_admin_can_query_anyone(self):
        """管理员可以查任何人。"""
        import tools.employee  # noqa: F401
        ctx = ToolContext(user_id=100, user_role="super_admin")
        result = await tool_registry.execute("query_employee_profile", {"user_id": 2}, ctx)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_reimbursement_query_self(self):
        """员工可以查自己的报销额度。"""
        import tools.reimbursement  # noqa: F401
        ctx = ToolContext(user_id=1, user_role="employee")
        result = await tool_registry.execute("query_reimbursement_limit", {"user_id": 1}, ctx)
        assert result.success is True
        assert "limits" in result.data

    @pytest.mark.asyncio
    async def test_reimbursement_query_specific_category(self):
        """可以指定查询类别。"""
        import tools.reimbursement  # noqa: F401
        ctx = ToolContext(user_id=1, user_role="employee")
        result = await tool_registry.execute(
            "query_reimbursement_limit",
            {"user_id": 1, "category": "差旅住宿"},
            ctx,
        )
        assert result.success is True
        assert result.data["category"] == "差旅住宿"
        assert "remaining" in result.data

    @pytest.mark.asyncio
    async def test_create_ticket_tool_registered(self):
        """create_it_ticket 工具已注册。"""
        import tools.ticket  # noqa: F401
        assert tool_registry.get("create_it_ticket") is not None

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        """调用不存在的工具返回错误。"""
        ctx = ToolContext(user_id=1, user_role="employee")
        result = await tool_registry.execute("nonexistent_tool", {}, ctx)
        assert result.success is False
        assert "not found" in result.error.lower() or "unknown" in result.error.lower()


@pytest.mark.no_db
class TestDecideToolNode:
    """测试工具决策节点。"""

    @pytest.mark.asyncio
    async def test_chitchat_skips_tool(self):
        """闲聊意图不触发工具。"""
        from graph.nodes import decide_tool_node
        state = _make_state("你好", intent="chitchat")
        result = await decide_tool_node(state)
        assert result["need_tool"] is False
