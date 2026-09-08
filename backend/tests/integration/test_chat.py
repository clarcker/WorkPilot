"""
对话聊天模块集成测试

测试范围：流式对话、会话管理
对应 API：/api/chat/*
严格对照 API 文档验证 HTTP 状态码和 SSE 事件格式
"""

import pytest
import json
from httpx import AsyncClient


class TestStreamChat:
    """流式对话测试 - POST /api/chat/stream"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_create_new_conversation(self, async_client: AsyncClient, employee_token: str, mock_ollama_chat, mock_ollama_embed):
        """CHAT-001: 创建新会话，SSE 流包含 conversation_id 事件"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        async with async_client.stream(
            "POST",
            "/api/chat/stream",
            json={"query": "报销规范是什么？"},
        ) as response:
            assert response.status_code == 200

            event_types = set()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        event_types.add(event.get("type"))
                    except json.JSONDecodeError:
                        pass

            assert "conversation_id" in event_types
            assert "done" in event_types

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_stream_returns_tokens(self, async_client: AsyncClient, employee_token: str, mock_ollama_chat, mock_ollama_embed):
        """CHAT-003: 流式对话返回 token 事件"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        async with async_client.stream(
            "POST",
            "/api/chat/stream",
            json={"query": "测试消息"},
        ) as response:
            has_token = False
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "token":
                            has_token = True
                            break
                    except json.JSONDecodeError:
                        pass

            assert has_token

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_stream_without_token(self, async_client: AsyncClient, mock_ollama_chat, mock_ollama_embed):
        """CHAT-009: 无 Token 对话返回 401"""
        response = await async_client.post(
            "/api/chat/stream",
            json={"query": "测试消息"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_stream_empty_message(self, async_client: AsyncClient, employee_token: str):
        """CHAT-011: 空消息返回 422"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.post(
            "/api/chat/stream",
            json={"query": ""},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_employee_can_chat(self, async_client: AsyncClient, employee_token: str, mock_ollama_chat, mock_ollama_embed):
        """CHAT-008: 员工可以进行对话"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        async with async_client.stream(
            "POST",
            "/api/chat/stream",
            json={"query": "测试"},
        ) as response:
            assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_can_chat(self, async_client: AsyncClient, dept_admin_token: str, mock_ollama_chat, mock_ollama_embed):
        """CHAT-015: 部门管理员可以进行对话"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        async with async_client.stream(
            "POST",
            "/api/chat/stream",
            json={"query": "测试"},
        ) as response:
            assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_super_admin_can_chat(self, async_client: AsyncClient, super_admin_token: str, mock_ollama_chat, mock_ollama_embed):
        """CHAT-016: 超管可以进行对话"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        async with async_client.stream(
            "POST",
            "/api/chat/stream",
            json={"query": "测试"},
        ) as response:
            assert response.status_code == 200


class TestConversationList:
    """会话列表测试 - GET /api/chat/conversations"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_list_conversations_success(self, async_client: AsyncClient, employee_token: str):
        """CHAT-016: 获取用户会话列表"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.get("/api/chat/conversations")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "items" in data["data"]
        assert "total" in data["data"]

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_list_conversations_pagination(self, async_client: AsyncClient, employee_token: str):
        """CHAT-017: 会话列表分页"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.get("/api/chat/conversations?page=1&page_size=10")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 10

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_list_conversations_without_token(self, async_client: AsyncClient):
        """CHAT-022: 无 Token 返回 401"""
        response = await async_client.get("/api/chat/conversations")

        assert response.status_code == 401


class TestConversationDetail:
    """会话详情测试 - GET /api/chat/conversations/{conv_id}"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_get_nonexistent_conversation(self, async_client: AsyncClient, employee_token: str):
        """CHAT-030: 查看不存在的会话返回 404"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.get("/api/chat/conversations/999999")

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_get_conversation_without_token(self, async_client: AsyncClient):
        """CHAT-031: 无 Token 返回 401"""
        response = await async_client.get("/api/chat/conversations/1")

        assert response.status_code == 401


class TestConversationDelete:
    """会话删除测试 - DELETE /api/chat/conversations/{conv_id}"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_delete_nonexistent_conversation(self, async_client: AsyncClient, employee_token: str):
        """CHAT-044: 删除不存在的会话返回 404"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.delete("/api/chat/conversations/999999")

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_delete_conversation_without_token(self, async_client: AsyncClient):
        """无 Token 返回 401"""
        response = await async_client.delete("/api/chat/conversations/1")

        assert response.status_code == 401
