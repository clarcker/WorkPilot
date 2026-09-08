from __future__ import annotations

import pytest

from tools.base import (
    ToolContext,
    ToolDef,
    ToolRegistry,
    ToolResult,
    make_idempotency_key,
    tool,
    tool_registry,
)


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(user_id=1, user_role="employee")


class TestToolRegistry:
    def test_register_and_get(self, registry: ToolRegistry) -> None:
        td = ToolDef(
            name="greet",
            description="Say hello",
            func=lambda args, ctx: "hi",
            permissions=[],
            params_schema={"type": "object", "properties": {}},
        )
        registry.register(td)
        assert registry.get("greet") is td
        assert registry.get("nonexistent") is None

    def test_duplicate_register_raises(self, registry: ToolRegistry) -> None:
        td = ToolDef(
            name="greet",
            description="Say hello",
            func=lambda args, ctx: "hi",
        )
        registry.register(td)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(td)

    def test_get_tools_for_prompt_filters_by_role(
        self, registry: ToolRegistry
    ) -> None:
        registry.register(
            ToolDef(
                name="public_tool",
                description="Visible to all",
                func=lambda a, c: None,
                permissions=[],
                params_schema={"type": "object", "properties": {}},
            )
        )
        registry.register(
            ToolDef(
                name="admin_tool",
                description="Admin only",
                func=lambda a, c: None,
                permissions=["admin"],
                params_schema={"type": "object", "properties": {}},
            )
        )
        emp_tools = registry.get_tools_for_prompt("employee")
        assert len(emp_tools) == 1
        assert emp_tools[0]["name"] == "public_tool"

        admin_tools = registry.get_tools_for_prompt("admin")
        assert len(admin_tools) == 2


class TestToolExecution:
    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, ctx: ToolContext) -> None:
        registry = ToolRegistry()
        result = await registry.execute("nope", {}, ctx)
        assert result.success is False
        assert "not found" in result.error  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_execute_permission_denied(
        self, registry: ToolRegistry, ctx: ToolContext
    ) -> None:
        registry.register(
            ToolDef(
                name="admin_only",
                description="Admin tool",
                func=lambda a, c: "ok",
                permissions=["admin"],
                params_schema={"type": "object", "properties": {}},
            )
        )
        result = await registry.execute("admin_only", {}, ctx)
        assert result.success is False
        assert result.deny_reason is not None
        assert "employee" in result.deny_reason

    @pytest.mark.asyncio
    async def test_execute_missing_required_param(
        self, registry: ToolRegistry, ctx: ToolContext
    ) -> None:
        registry.register(
            ToolDef(
                name="needs_name",
                description="Needs name",
                func=lambda a, c: a["name"],
                permissions=[],
                params_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            )
        )
        result = await registry.execute("needs_name", {}, ctx)
        assert result.success is False
        assert "Missing required parameter" in result.error  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_execute_success(
        self, registry: ToolRegistry, ctx: ToolContext
    ) -> None:
        async def echo(args: dict, c: ToolContext) -> str:
            return f"hello {args['name']}"

        registry.register(
            ToolDef(
                name="echo",
                description="Echo",
                func=echo,
                permissions=[],
                params_schema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            )
        )
        result = await registry.execute("echo", {"name": "world"}, ctx)
        assert result.success is True
        assert result.data == "hello world"


class TestIdempotencyKey:
    def test_deterministic(self) -> None:
        k1 = make_idempotency_key(1, action="create", title="test")
        k2 = make_idempotency_key(1, action="create", title="test")
        assert k1 == k2

    def test_different_inputs(self) -> None:
        k1 = make_idempotency_key(1, action="create")
        k2 = make_idempotency_key(2, action="create")
        assert k1 != k2


class TestToolDecorator:
    def test_decorator_registers_tool(self) -> None:
        @tool(name="dummy", description="A dummy tool")
        async def dummy(args: dict, ctx: ToolContext) -> str:
            return "ok"

        td = tool_registry.get("dummy")
        assert td is not None
        assert td.name == "dummy"
        assert td.description == "A dummy tool"
        assert hasattr(dummy, "_tool_def")

        # cleanup
        del tool_registry._tools["dummy"]
