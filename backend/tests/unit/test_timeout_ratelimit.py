"""工具执行超时 + 限流中间件。"""
from __future__ import annotations

import asyncio

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from core.ratelimit import RateLimitMiddleware
from tools.base import ToolContext, ToolDef, ToolRegistry


@pytest.mark.no_db
class TestToolTimeout:
    @pytest.mark.asyncio
    async def test_slow_tool_times_out(self):
        registry = ToolRegistry()

        async def slow_tool(args, ctx):
            await asyncio.sleep(2.0)
            return {"ok": True}

        registry.register(
            ToolDef(
                name="slow",
                description="sleeps",
                func=slow_tool,
                permissions=[],
                params_schema={"type": "object", "properties": {}},
            )
        )
        ctx = ToolContext(user_id=1, user_role="employee")
        result = await registry.execute("slow", {}, ctx, timeout=0.05)
        assert result.success is False
        assert "timed out" in (result.error or "")

    @pytest.mark.asyncio
    async def test_fast_tool_completes(self):
        registry = ToolRegistry()

        async def fast_tool(args, ctx):
            return {"value": 42}

        registry.register(
            ToolDef(
                name="fast",
                description="quick",
                func=fast_tool,
                permissions=[],
                params_schema={"type": "object", "properties": {}},
            )
        )
        ctx = ToolContext(user_id=1, user_role="employee")
        result = await registry.execute("fast", {}, ctx, timeout=1.0)
        assert result.success is True
        assert result.data == {"value": 42}

    @pytest.mark.asyncio
    async def test_integer_coercion_still_works_under_timeout_path(self):
        registry = ToolRegistry()

        async def echo_id(args, ctx):
            return {"user_id": args["user_id"], "type": type(args["user_id"]).__name__}

        registry.register(
            ToolDef(
                name="echo_id",
                description="echo",
                func=echo_id,
                permissions=[],
                params_schema={
                    "type": "object",
                    "properties": {"user_id": {"type": "integer"}},
                    "required": ["user_id"],
                },
            )
        )
        ctx = ToolContext(user_id=1, user_role="employee")
        result = await registry.execute("echo_id", {"user_id": "7"}, ctx, timeout=1.0)
        assert result.success is True
        assert result.data["user_id"] == 7
        assert result.data["type"] == "int"


def _make_app(login_limit: int = 3, chat_limit: int = 2) -> Starlette:
    async def login(request):
        return JSONResponse({"ok": True})

    async def chat(request):
        return JSONResponse({"ok": True})

    async def health(request):
        return JSONResponse({"ok": True})

    app = Starlette(
        routes=[
            Route("/api/auth/login", login, methods=["POST"]),
            Route("/api/chat/stream", chat, methods=["POST"]),
            Route("/health", health),
        ]
    )
    app.add_middleware(
        RateLimitMiddleware,
        login_per_minute=login_limit,
        chat_per_5min=chat_limit,
    )
    return app


@pytest.mark.no_db
class TestRateLimitMiddleware:
    def test_login_allowed_then_blocked(self):
        client = TestClient(_make_app(login_limit=3))
        for i in range(3):
            r = client.post("/api/auth/login", json={})
            assert r.status_code == 200, f"request {i+1} should pass"
        r = client.post("/api/auth/login", json={})
        assert r.status_code == 429
        body = r.json()
        assert body["code"] == 42901
        assert "频繁" in body["message"]

    def test_chat_blocked_after_limit(self):
        client = TestClient(_make_app(chat_limit=2))
        headers = {"Authorization": "Bearer " + "x" * 40}
        for _ in range(2):
            r = client.post("/api/chat/stream", json={}, headers=headers)
            assert r.status_code == 200
        r = client.post("/api/chat/stream", json={}, headers=headers)
        assert r.status_code == 429
        assert r.json()["code"] == 42902

    def test_health_not_rate_limited(self):
        client = TestClient(_make_app(login_limit=1))
        for _ in range(5):
            assert client.get("/health").status_code == 200

    def test_different_tokens_are_independent(self):
        client = TestClient(_make_app(chat_limit=1))
        h1 = {"Authorization": "Bearer " + "a" * 40}
        h2 = {"Authorization": "Bearer " + "b" * 40}
        assert client.post("/api/chat/stream", json={}, headers=h1).status_code == 200
        assert client.post("/api/chat/stream", json={}, headers=h1).status_code == 429
        assert client.post("/api/chat/stream", json={}, headers=h2).status_code == 200
