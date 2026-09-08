"""
端到端完整工作流测试

测试范围：从登录到对话的完整业务流程
"""

import pytest
from httpx import AsyncClient
from io import BytesIO
import json


class TestCompleteWorkflow:
    """完整业务流程端到端测试"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_login_upload_chat_complete_flow(
        self,
        async_client: AsyncClient,
        super_admin_token: str,
        employee_user,
        tech_department,
        mock_file_storage,
        mock_ollama_embed,
        mock_ollama_chat,
    ):
        """完整工作流：超管上传文档，员工登录并对话"""

        # 步骤 1：管理员上传文档
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        md_content = "# 出差规范\n\n住宿报销上限为 500 元每晚。".encode("utf-8")
        files = {"file": ("travel.md", BytesIO(md_content), "text/markdown")}

        upload_response = await async_client.post(
            "/api/docs/upload",
            files=files,
            data={
                "dept_id": str(tech_department.id),
                "visibility": "global",
                "category": "规范",
                "version": "v1.0",
            },
        )

        assert upload_response.status_code == 201
        upload_data = upload_response.json()
        assert upload_data["code"] == 0
        doc_id = upload_data["data"]["id"]

        # 步骤 2：员工登录
        login_response = await async_client.post(
            "/api/auth/login",
            json={"username": employee_user.username, "password": "Employee@123"},
        )

        login_data = login_response.json()
        assert login_data["code"] == 0
        employee_token = login_data["data"]["access_token"]

        # 步骤 3：员工查看自己的信息
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        me_response = await async_client.get("/api/auth/me")
        assert me_response.status_code == 200
        assert me_response.json()["code"] == 0
        assert me_response.json()["data"]["username"] == employee_user.username

        # 步骤 4：员工发起对话（流式）
        async with async_client.stream(
            "POST",
            "/api/chat/stream",
            json={"query": "报销住宿的上限是多少？"},
        ) as response:
            assert response.status_code == 200

            event_types = set()
            conversation_id = None

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        event_type = event.get("type")
                        event_types.add(event_type)

                        if event_type == "conversation_id":
                            conversation_id = event.get("content")
                    except json.JSONDecodeError:
                        pass

            assert "conversation_id" in event_types
            assert "done" in event_types
            assert conversation_id is not None

        # 步骤 5：员工查看会话列表
        conversations_response = await async_client.get("/api/chat/conversations")
        assert conversations_response.status_code == 200
        assert conversations_response.json()["code"] == 0

        # 步骤 6：员工登出
        logout_response = await async_client.post("/api/auth/logout")
        assert logout_response.status_code == 200
        assert logout_response.json()["code"] == 0

        # 步骤 7：验证登出后 Token 失效
        me_response_after = await async_client.get("/api/auth/me")
        assert me_response_after.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_admin_management_workflow(
        self,
        async_client: AsyncClient,
        super_admin_token: str,
    ):
        """完整管理流程：创建部门、创建用户"""

        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        # 步骤 1：创建新部门
        create_dept_resp = await async_client.post(
            "/api/admin/departments",
            json={"dept_code": "NEWDEPT", "dept_name": "新部门"},
        )

        assert create_dept_resp.status_code == 201
        dept_data = create_dept_resp.json()
        assert dept_data["code"] == 0
        new_dept_id = dept_data["data"]["id"]

        # 步骤 2：创建用户
        create_user_resp = await async_client.post(
            "/api/admin/users",
            json={
                "real_name": "新员工",
                "username": "newemployee",
                "employee_no": "NEW001",
                "dept_id": new_dept_id,
                "role": "employee",
            },
        )

        assert create_user_resp.status_code == 201
        user_data = create_user_resp.json()
        assert user_data["code"] == 0
        new_user_id = user_data["data"]["id"]
        temp_password = user_data["data"]["init_password"]

        # 步骤 3：查看部门列表
        dept_list_resp = await async_client.get("/api/admin/departments")
        assert dept_list_resp.status_code == 200
        assert dept_list_resp.json()["code"] == 0

        # 步骤 4：查看用户列表
        user_list_resp = await async_client.get("/api/admin/users")
        assert user_list_resp.status_code == 200
        assert user_list_resp.json()["code"] == 0

        # 步骤 5：修改用户信息
        update_user_resp = await async_client.patch(
            f"/api/admin/users/{new_user_id}",
            json={"display_name": "新员工·更新"},
        )
        assert update_user_resp.status_code == 200
        assert update_user_resp.json()["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_permission_workflow(
        self,
        async_client: AsyncClient,
        super_admin_token: str,
        dept_admin_token: str,
        employee_token: str,
    ):
        """权限管理流程：不同角色权限验证"""

        # 超管操作
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        super_admin_ops = [
            ("GET", "/api/admin/departments"),
            ("GET", "/api/admin/users"),
        ]

        for method, endpoint in super_admin_ops:
            response = await async_client.request(method, endpoint)
            assert response.status_code == 200
            assert response.json()["code"] == 0

        # 部门管理员操作
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        # 可以访问用户列表
        user_list_resp = await async_client.get("/api/admin/users")
        assert user_list_resp.status_code == 200

        # 不能访问部门列表
        dept_list_resp = await async_client.get("/api/admin/departments")
        assert dept_list_resp.status_code == 403

        # 员工操作
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        # 不能访问管理接口
        for endpoint in ["/api/admin/departments", "/api/admin/users"]:
            response = await async_client.get(endpoint)
            assert response.status_code == 403

        # 可以访问聊天接口
        chat_resp = await async_client.get("/api/chat/conversations")
        assert chat_resp.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_health_check(self, async_client: AsyncClient):
        """健康检查接口"""
        async_client.headers.pop("Authorization", None)

        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
