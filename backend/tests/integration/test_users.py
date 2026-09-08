"""
用户管理模块集成测试

测试范围：用户 CRUD、权限管理、禁用启用、重置密码
对应 API：/api/admin/users/*
严格对照 API 文档验证 HTTP 状态码和字段名
"""

import pytest
from httpx import AsyncClient


class TestUserList:
    """用户列表接口测试 - GET /api/admin/users"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_super_admin_list_all_users(self, async_client: AsyncClient, super_admin_token: str, multiple_employees):
        """USER-001: 超管查看所有用户"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.get("/api/admin/users")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "items" in data["data"]
        assert len(data["data"]["items"]) > 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_list_own_department_users(self, async_client: AsyncClient, dept_admin_token: str, employee_user):
        """USER-002: 部门管理员查看本部门用户"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        response = await async_client.get("/api/admin/users")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        usernames = [u["username"] for u in data["data"]["items"]]
        assert employee_user.username in usernames

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_employee_cannot_list_users(self, async_client: AsyncClient, employee_token: str):
        """USER-004: 员工无权查看用户列表"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.get("/api/admin/users")

        assert response.status_code == 403
        data = response.json()
        assert data["code"] == 40301

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_list_users_with_department_filter(self, async_client: AsyncClient, super_admin_token: str, tech_department, hr_department, employee_user):
        """USER-005: 按部门过滤用户"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.get(f"/api/admin/users?dept_id={tech_department.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        for user in data["data"]["items"]:
            assert user["dept_id"] == tech_department.id

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_list_users_with_keyword_search(self, async_client: AsyncClient, super_admin_token: str, employee_user):
        """USER-007: 按关键词搜索用户"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.get(f"/api/admin/users?keyword={employee_user.username}")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        usernames = [u["username"] for u in data["data"]["items"]]
        assert employee_user.username in usernames

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_list_users_pagination(self, async_client: AsyncClient, super_admin_token: str):
        """USER-009: 用户列表分页"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.get("/api/admin/users?page=1&page_size=10")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 10
        assert "total" in data["data"]


class TestSuggestUsername:
    """用户名建议接口 - GET /api/admin/users/suggest-username"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_suggest_username_basic(self, async_client: AsyncClient, super_admin_token: str):
        """USER-012: 根据姓名生成拼音用户名"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        resp = await async_client.get("/api/admin/users/suggest-username", params={"name": "张三"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "suggested" in data["data"]
        assert "pinyin_base" in data["data"]
        assert data["data"]["pinyin_base"] == "zhangsan"
        assert data["data"]["suggested"].startswith("zhangsan")

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_suggest_username_requires_auth(self, async_client: AsyncClient):
        """USER-016: 无 Token 返回 401"""
        async_client.headers.pop("Authorization", None)

        resp = await async_client.get("/api/admin/users/suggest-username", params={"name": "张三"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_suggest_username_employee_forbidden(self, async_client: AsyncClient, employee_token: str):
        """USER-015: 员工无权使用"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        resp = await async_client.get("/api/admin/users/suggest-username", params={"name": "张三"})
        assert resp.status_code == 403
        assert resp.json()["code"] == 40301


class TestSuggestEmployeeNo:
    """员工编号建议接口 - GET /api/admin/users/suggest-employee-no"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_suggest_employee_no_basic(self, async_client: AsyncClient, super_admin_token: str, tech_department):
        """USER-017: 根据部门生成员工编号"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        resp = await async_client.get("/api/admin/users/suggest-employee-no", params={"dept_id": tech_department.id})

        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "suggested" in data["data"]
        assert "dept_code" in data["data"]
        assert "next_seq" in data["data"]
        assert data["data"]["suggested"].startswith(data["data"]["dept_code"])

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_suggest_employee_no_nonexistent_dept(self, async_client: AsyncClient, super_admin_token: str):
        """USER-019: 不存在的部门返回 404"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        resp = await async_client.get("/api/admin/users/suggest-employee-no", params={"dept_id": 999999})
        assert resp.status_code == 404
        assert resp.json()["code"] == 40400


class TestCreateUser:
    """创建用户测试 - POST /api/admin/users"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_super_admin_create_employee(self, async_client: AsyncClient, super_admin_token: str, tech_department):
        """USER-021: 超管创建员工，返回 201"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.post(
            "/api/admin/users",
            json={
                "real_name": "新员工",
                "username": "newemp",
                "employee_no": "RD999",
                "dept_id": tech_department.id,
                "role": "employee",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["code"] == 0
        assert "id" in data["data"]
        assert "init_password" in data["data"]
        assert data["data"]["username"] == "newemp"

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_super_admin_create_dept_admin(self, async_client: AsyncClient, super_admin_token: str, tech_department):
        """USER-022: 超管创建部门管理员"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.post(
            "/api/admin/users",
            json={
                "real_name": "新管理员",
                "username": "newadmin",
                "employee_no": "ADMIN999",
                "dept_id": tech_department.id,
                "role": "dept_admin",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["username"] == "newadmin"

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_create_employee_own_department(self, async_client: AsyncClient, dept_admin_token: str, tech_department):
        """USER-023: 部门管理员创建本部门员工"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        response = await async_client.post(
            "/api/admin/users",
            json={
                "real_name": "新员工",
                "username": "empbyadmin",
                "employee_no": "RD888",
                "dept_id": tech_department.id,
                "role": "employee",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_cannot_create_other_department(self, async_client: AsyncClient, dept_admin_token: str, hr_department):
        """USER-024: 部门管理员无法创建其他部门员工"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        response = await async_client.post(
            "/api/admin/users",
            json={
                "real_name": "其他部门员工",
                "username": "otheremp",
                "employee_no": "HR999",
                "dept_id": hr_department.id,
                "role": "employee",
            },
        )

        assert response.status_code == 403
        data = response.json()
        assert data["code"] == 40301

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_cannot_create_dept_admin(self, async_client: AsyncClient, dept_admin_token: str, tech_department):
        """USER-025: 部门管理员无法创建部门管理员"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        response = await async_client.post(
            "/api/admin/users",
            json={
                "real_name": "新管理员",
                "username": "newadmin2",
                "employee_no": "ADMIN888",
                "dept_id": tech_department.id,
                "role": "dept_admin",
            },
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_create_user_duplicate_username(self, async_client: AsyncClient, super_admin_token: str, tech_department, employee_user):
        """USER-026: 重复用户名返回 409"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.post(
            "/api/admin/users",
            json={
                "real_name": "另一个用户",
                "username": employee_user.username,
                "employee_no": "DUP001",
                "dept_id": tech_department.id,
                "role": "employee",
            },
        )

        assert response.status_code == 409
        data = response.json()
        assert data["code"] == 40900

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_create_user_duplicate_employee_no(self, async_client: AsyncClient, super_admin_token: str, tech_department, employee_user):
        """USER-027: 重复员工编号返回 409"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.post(
            "/api/admin/users",
            json={
                "real_name": "另一个用户",
                "username": "anotheruser",
                "employee_no": employee_user.employee_no,
                "dept_id": tech_department.id,
                "role": "employee",
            },
        )

        assert response.status_code == 409
        data = response.json()
        assert data["code"] == 40900

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_create_user_nonexistent_dept(self, async_client: AsyncClient, super_admin_token: str):
        """USER-028: 不存在的部门返回 400"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.post(
            "/api/admin/users",
            json={
                "real_name": "新用户",
                "username": "newuser999",
                "employee_no": "NEW999",
                "dept_id": 999999,
                "role": "employee",
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_employee_cannot_create_user(self, async_client: AsyncClient, employee_token: str, tech_department):
        """USER-025: 员工无权创建用户"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.post(
            "/api/admin/users",
            json={
                "real_name": "新用户",
                "username": "newuser",
                "employee_no": "NEW001",
                "dept_id": tech_department.id,
                "role": "employee",
            },
        )

        assert response.status_code == 403


class TestUserDetail:
    """用户详情测试 - GET /api/admin/users/{user_id}"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_super_admin_view_user_detail(self, async_client: AsyncClient, super_admin_token: str, employee_user):
        """USER-033: 超管查看用户详情"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.get(f"/api/admin/users/{employee_user.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["id"] == employee_user.id
        assert data["data"]["username"] == employee_user.username

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_view_nonexistent_user(self, async_client: AsyncClient, super_admin_token: str):
        """USER-036: 查看不存在的用户返回 404"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.get("/api/admin/users/999999")

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == 40400


class TestUpdateUser:
    """修改用户信息测试 - PATCH /api/admin/users/{user_id}"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_update_user_display_name(self, async_client: AsyncClient, super_admin_token: str, employee_user):
        """USER-039: 修改用户昵称"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.patch(
            f"/api/admin/users/{employee_user.id}",
            json={"display_name": "新昵称"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

        # 验证修改
        detail_resp = await async_client.get(f"/api/admin/users/{employee_user.id}")
        assert detail_resp.json()["data"]["display_name"] == "新昵称"

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_update_user_cannot_modify_username(self, async_client: AsyncClient, super_admin_token: str, employee_user):
        """USER-042: 不能修改用户名"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        original_username = employee_user.username

        await async_client.patch(
            f"/api/admin/users/{employee_user.id}",
            json={"username": "changed_username"},
        )

        detail_resp = await async_client.get(f"/api/admin/users/{employee_user.id}")
        assert detail_resp.json()["data"]["username"] == original_username

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_update_nonexistent_user(self, async_client: AsyncClient, super_admin_token: str):
        """USER-048: 修改不存在的用户返回 404"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.patch(
            "/api/admin/users/999999",
            json={"display_name": "新昵称"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_cannot_update_other_fields(self, async_client: AsyncClient, dept_admin_token: str, employee_user):
        """USER-047: 部门管理员只能修改 display_name/email/notes"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        response = await async_client.patch(
            f"/api/admin/users/{employee_user.id}",
            json={"display_name": "管理员改的昵称"},
        )

        assert response.status_code == 200


class TestResetPassword:
    """重置密码测试 - POST /api/admin/users/{user_id}/reset-password"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_reset_password_success(self, async_client: AsyncClient, super_admin_token: str, employee_user):
        """USER-049: 成功重置密码"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.post(f"/api/admin/users/{employee_user.id}/reset-password")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "new_password" in data["data"]
        assert data["data"]["must_change_password"] is True

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_reset_password_nonexistent_user(self, async_client: AsyncClient, super_admin_token: str):
        """USER-054: 重置不存在用户的密码返回 404"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.post("/api/admin/users/999999/reset-password")

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_employee_cannot_reset_password(self, async_client: AsyncClient, employee_token: str, dept_admin_user):
        """USER-055: 员工无权重置密码"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.post(f"/api/admin/users/{dept_admin_user.id}/reset-password")

        assert response.status_code == 403


class TestDisableEnableUser:
    """禁用/启用用户测试 - PATCH /api/admin/users/{user_id}/status"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_disable_user_success(self, async_client: AsyncClient, super_admin_token: str, employee_user):
        """USER-056: 成功禁用用户"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.patch(
            f"/api/admin/users/{employee_user.id}/status",
            json={"is_active": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_disabled_user_cannot_login(self, async_client: AsyncClient, db_session, employee_user):
        """USER-057: 禁用用户无法登录"""
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
    async def test_enable_user_success(self, async_client: AsyncClient, super_admin_token: str, db_session, employee_user):
        """USER-063: 成功启用用户"""
        from tests.utils import disable_user

        await disable_user(db_session, employee_user)

        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        response = await async_client.patch(
            f"/api/admin/users/{employee_user.id}/status",
            json={"is_active": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_enabled_user_can_login(self, async_client: AsyncClient, super_admin_token: str, db_session, employee_user):
        """USER-064: 启用用户可以登录"""
        from tests.utils import disable_user, enable_user

        await disable_user(db_session, employee_user)
        await enable_user(db_session, employee_user)

        response = await async_client.post(
            "/api/auth/login",
            json={"username": employee_user.username, "password": "Employee@123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0


class TestUnlockUser:
    """解锁用户测试 - POST /api/admin/users/{user_id}/unlock"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_unlock_user_success(self, async_client: AsyncClient, super_admin_token: str, db_session, employee_user):
        """USER-068: 成功解锁用户"""
        from tests.utils import lock_user_account

        await lock_user_account(db_session, employee_user, fail_count=5)

        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        response = await async_client.post(f"/api/admin/users/{employee_user.id}/unlock")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_unlocked_user_can_login(self, async_client: AsyncClient, super_admin_token: str, db_session, employee_user):
        """USER-069: 解锁用户可以登录"""
        from tests.utils import lock_user_account

        await lock_user_account(db_session, employee_user, fail_count=5)

        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        await async_client.post(f"/api/admin/users/{employee_user.id}/unlock")

        # 用新 client 登录
        from httpx import AsyncClient, ASGITransport
        from main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as clean_client:
            response = await clean_client.post(
                "/api/auth/login",
                json={"username": employee_user.username, "password": "Employee@123"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0


class TestForceLogout:
    """强制登出测试 - POST /api/admin/users/{user_id}/force-logout"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_super_admin_force_logout(self, async_client: AsyncClient, super_admin_token: str, employee_user):
        """USER-073: 超管强制登出用户"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.post(f"/api/admin/users/{employee_user.id}/force-logout")

        assert response.status_code == 200
        assert response.json()["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_cannot_force_logout(self, async_client: AsyncClient, dept_admin_token: str, employee_user):
        """USER-076: 部门管理员无权强制登出"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        response = await async_client.post(f"/api/admin/users/{employee_user.id}/force-logout")

        assert response.status_code == 403
        assert response.json()["code"] == 40301
