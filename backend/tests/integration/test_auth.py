"""
认证模块集成测试

测试范围：登录、登出、Token 刷新、密码修改、用户信息
对应 API：/api/auth/*
严格对照 API 文档验证 HTTP 状态码和响应结构
"""

import pytest
from httpx import AsyncClient
from db.models import User


class TestLogin:
    """登录接口测试 - POST /api/auth/login"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_login_success(self, async_client: AsyncClient, employee_user: User):
        """AUTH-001: 成功登录返回 token 和用户信息"""
        response = await async_client.post(
            "/api/auth/login",
            json={"username": employee_user.username, "password": "Employee@123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "access_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
        assert data["data"]["expires_in"] > 0
        assert data["data"]["user"]["username"] == employee_user.username
        assert data["data"]["user"]["role"] == "employee"

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_login_wrong_password(self, async_client: AsyncClient, employee_user: User):
        """AUTH-002: 密码错误返回 401"""
        response = await async_client.post(
            "/api/auth/login",
            json={"username": employee_user.username, "password": "WrongPassword"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == 40001

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_login_user_not_exist(self, async_client: AsyncClient):
        """AUTH-003: 用户不存在返回 401"""
        response = await async_client.post(
            "/api/auth/login",
            json={"username": "nonexistent_user", "password": "Password@123"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == 40001

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_login_disabled_account(self, async_client: AsyncClient, db_session, employee_user: User):
        """AUTH-004: 禁用账户返回 403"""
        from tests.utils import disable_user

        await disable_user(db_session, employee_user)

        response = await async_client.post(
            "/api/auth/login",
            json={"username": employee_user.username, "password": "Employee@123"},
        )

        assert response.status_code == 403
        data = response.json()
        assert data["code"] == 40003

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_login_locked_account(self, async_client: AsyncClient, db_session, employee_user: User):
        """AUTH-005: 锁定账户返回 403"""
        from tests.utils import lock_user_account

        await lock_user_account(db_session, employee_user, fail_count=5)

        response = await async_client.post(
            "/api/auth/login",
            json={"username": employee_user.username, "password": "Employee@123"},
        )

        assert response.status_code == 403
        data = response.json()
        assert data["code"] == 40002

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_login_must_change_password(self, async_client: AsyncClient, db_session, employee_user: User):
        """AUTH-006: 首次登录 must_change_password=true"""
        from tests.utils import set_must_change_password

        await set_must_change_password(db_session, employee_user, must_change=True)

        response = await async_client.post(
            "/api/auth/login",
            json={"username": employee_user.username, "password": "Employee@123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["must_change_password"] is True

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_login_consecutive_failures_lock(self, async_client: AsyncClient, employee_user: User):
        """AUTH-009: 连续 5 次失败登录后锁定"""
        for i in range(5):
            await async_client.post(
                "/api/auth/login",
                json={"username": employee_user.username, "password": "WrongPassword"},
            )

        # 第 6 次应该被锁定
        response = await async_client.post(
            "/api/auth/login",
            json={"username": employee_user.username, "password": "WrongPassword"},
        )
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == 40002

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_login_token_usable(self, async_client: AsyncClient, employee_user: User):
        """AUTH-010: 登录返回的 Token 可用于后续请求"""
        login_resp = await async_client.post(
            "/api/auth/login",
            json={"username": employee_user.username, "password": "Employee@123"},
        )
        token = login_resp.json()["data"]["access_token"]

        async_client.headers.update({"Authorization": f"Bearer {token}"})
        me_resp = await async_client.get("/api/auth/me")

        assert me_resp.status_code == 200
        assert me_resp.json()["data"]["username"] == employee_user.username


class TestLogout:
    """登出接口测试 - POST /api/auth/logout"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_logout_success(self, async_client: AsyncClient, employee_token: str):
        """AUTH-011: 正常登出"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.post("/api/auth/logout")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_logout_revokes_token(self, async_client: AsyncClient, employee_token: str):
        """AUTH-012: 登出后 Token 失效"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        await async_client.post("/api/auth/logout")

        # 用同一 Token 调用其他接口应失败
        me_resp = await async_client.get("/api/auth/me")
        assert me_resp.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_logout_without_token(self, async_client: AsyncClient):
        """AUTH-013: 无 Token 登出返回 401"""
        response = await async_client.post("/api/auth/logout")

        assert response.status_code == 401


class TestTokenRefresh:
    """Token 刷新测试 - POST /api/auth/refresh"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_token_refresh_success(self, async_client: AsyncClient, employee_token: str):
        """AUTH-016: 正常刷新 Token"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.post("/api/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "access_token" in data["data"]
        new_token = data["data"]["access_token"]
        assert new_token != employee_token

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_token_refresh_revokes_old(self, async_client: AsyncClient, employee_token: str):
        """AUTH-020: 刷新后旧 Token 失效"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        refresh_resp = await async_client.post("/api/auth/refresh")
        new_token = refresh_resp.json()["data"]["access_token"]

        # 旧 Token 应失效
        me_resp = await async_client.get("/api/auth/me")
        assert me_resp.status_code == 401

        # 新 Token 应可用
        async_client.headers.update({"Authorization": f"Bearer {new_token}"})
        new_me_resp = await async_client.get("/api/auth/me")
        assert new_me_resp.status_code == 200
        assert new_me_resp.json()["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_token_refresh_without_token(self, async_client: AsyncClient):
        """AUTH-018: 无 Token 刷新返回 401"""
        response = await async_client.post("/api/auth/refresh")

        assert response.status_code == 401


class TestChangePassword:
    """修改密码测试 - POST /api/auth/change-password"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_change_password_success(self, async_client: AsyncClient, employee_token: str):
        """AUTH-021: 成功修改密码"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.post(
            "/api/auth/change-password",
            json={"old_password": "Employee@123", "new_password": "NewPassword@456"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_change_password_wrong_old(self, async_client: AsyncClient, employee_token: str):
        """AUTH-022: 旧密码错误返回 400"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.post(
            "/api/auth/change-password",
            json={"old_password": "WrongOldPassword", "new_password": "NewPassword@456"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == 40001

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_change_password_first_time(self, async_client: AsyncClient, db_session, employee_user: User):
        """AUTH-023: 首次改密可不传旧密码"""
        from tests.utils import set_must_change_password
        from core.security import create_access_token

        await set_must_change_password(db_session, employee_user, must_change=True)

        token, _, _ = create_access_token(user_id=employee_user.id, role=employee_user.role)
        async_client.headers.update({"Authorization": f"Bearer {token}"})

        response = await async_client.post(
            "/api/auth/change-password",
            json={"new_password": "NewPassword@456"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_change_password_same_as_old(self, async_client: AsyncClient, employee_token: str):
        """AUTH-025: 新密码与旧密码相同返回 400"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.post(
            "/api/auth/change-password",
            json={"old_password": "Employee@123", "new_password": "Employee@123"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["code"] == 42200

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_change_password_without_token(self, async_client: AsyncClient):
        """AUTH-026: 无 Token 修改密码返回 401"""
        response = await async_client.post(
            "/api/auth/change-password",
            json={"old_password": "Old", "new_password": "New@123"},
        )

        assert response.status_code == 401


class TestGetUserInfo:
    """获取用户信息测试 - GET /api/auth/me"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_get_user_info_success(self, async_client: AsyncClient, employee_token: str, employee_user: User):
        """AUTH-028: 成功获取用户信息"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.get("/api/auth/me")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        user_data = data["data"]
        assert user_data["id"] == employee_user.id
        assert user_data["username"] == employee_user.username
        assert user_data["role"] == "employee"
        assert "display_name" in user_data
        assert "dept_id" in user_data
        assert "employee_no" in user_data
        assert "real_name" in user_data

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_get_user_info_no_token(self, async_client: AsyncClient):
        """AUTH-030: 无 Token 返回 401"""
        response = await async_client.get("/api/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_get_user_info_expired_token(self, async_client: AsyncClient):
        """AUTH-031: 过期 Token 返回 401"""
        from tests.utils import create_expired_token

        expired_token = create_expired_token(user_id=1, hours=-1)
        async_client.headers.update({"Authorization": f"Bearer {expired_token}"})

        response = await async_client.get("/api/auth/me")

        assert response.status_code == 401


class TestUpdateUserInfo:
    """修改用户信息测试 - PATCH /api/auth/me"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_update_display_name_success(self, async_client: AsyncClient, employee_token: str):
        """AUTH-033: 成功修改昵称"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.patch(
            "/api/auth/me",
            json={"display_name": "新昵称"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

        # 验证修改生效
        me_resp = await async_client.get("/api/auth/me")
        assert me_resp.json()["data"]["display_name"] == "新昵称"

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_update_try_modify_username(self, async_client: AsyncClient, employee_token: str, employee_user: User):
        """AUTH-035: 尝试修改用户名应被忽略"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        await async_client.patch(
            "/api/auth/me",
            json={"username": "new_username"},
        )

        # 用户名不应改变
        me_resp = await async_client.get("/api/auth/me")
        assert me_resp.json()["data"]["username"] == employee_user.username

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_update_without_token(self, async_client: AsyncClient):
        """AUTH-038: 无 Token 修改返回 401"""
        response = await async_client.patch(
            "/api/auth/me",
            json={"display_name": "新昵称"},
        )

        assert response.status_code == 401


class TestConcurrentLogin:
    """并发登录测试（边界场景）"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_same_user_multiple_tokens(self, async_client: AsyncClient, employee_user: User):
        """AUTH-B01: 同一用户多端登录，多个 Token 均有效"""
        from httpx import AsyncClient, ASGITransport
        from main import app

        # 第一次登录
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client1:
            resp1 = await client1.post(
                "/api/auth/login",
                json={"username": employee_user.username, "password": "Employee@123"},
            )
            token1 = resp1.json()["data"]["access_token"]

        # 第二次登录
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client2:
            resp2 = await client2.post(
                "/api/auth/login",
                json={"username": employee_user.username, "password": "Employee@123"},
            )
            token2 = resp2.json()["data"]["access_token"]

        # 两个 Token 应该不同但都有效
        assert token1 != token2

        # 两个 Token 都能访问 /me
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            client.headers.update({"Authorization": f"Bearer {token1}"})
            me1 = await client.get("/api/auth/me")
            assert me1.status_code == 200

            client.headers.update({"Authorization": f"Bearer {token2}"})
            me2 = await client.get("/api/auth/me")
            assert me2.status_code == 200
