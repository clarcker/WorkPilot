"""
部门管理模块集成测试

测试范围：部门 CRUD、权限管理
对应 API：/api/admin/departments/*
严格对照 API 文档验证 HTTP 状态码
"""

import pytest
from httpx import AsyncClient


class TestDepartmentList:
    """部门列表接口测试 - GET /api/admin/departments"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_super_admin_list_departments(self, async_client: AsyncClient, super_admin_token: str, multiple_departments):
        """DEPT-001: 超管可以查看所有部门"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.get("/api/admin/departments")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert len(data["data"]) >= 2

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_cannot_list_departments(self, async_client: AsyncClient, dept_admin_token: str):
        """DEPT-002: 部门管理员无权访问部门列表（仅超管）"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        response = await async_client.get("/api/admin/departments")

        assert response.status_code == 403
        data = response.json()
        assert data["code"] == 40301

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_employee_cannot_list_departments(self, async_client: AsyncClient, employee_token: str):
        """DEPT-003: 员工无权访问部门列表"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.get("/api/admin/departments")

        assert response.status_code == 403
        data = response.json()
        assert data["code"] == 40301

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_department_includes_user_count(self, async_client: AsyncClient, super_admin_token: str, tech_department, multiple_employees):
        """DEPT-005: 部门列表包含成员数量"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.get("/api/admin/departments")

        assert response.status_code == 200
        data = response.json()
        depts = data["data"]
        tech_dept = next(d for d in depts if d["id"] == tech_department.id)
        assert "user_count" in tech_dept
        assert tech_dept["user_count"] >= 3


class TestCreateDepartment:
    """创建部门测试 - POST /api/admin/departments"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_super_admin_create_department(self, async_client: AsyncClient, super_admin_token: str):
        """DEPT-007: 超管创建部门成功，返回 201"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.post(
            "/api/admin/departments",
            json={"dept_code": "SALES", "dept_name": "销售部"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["dept_code"] == "SALES"
        assert data["data"]["dept_name"] == "销售部"

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_cannot_create_department(self, async_client: AsyncClient, dept_admin_token: str):
        """DEPT-008: 部门管理员无权创建部门"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        response = await async_client.post(
            "/api/admin/departments",
            json={"dept_code": "TEST", "dept_name": "测试部"},
        )

        assert response.status_code == 403
        data = response.json()
        assert data["code"] == 40301

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_employee_cannot_create_department(self, async_client: AsyncClient, employee_token: str):
        """DEPT-009: 员工无权创建部门"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})

        response = await async_client.post(
            "/api/admin/departments",
            json={"dept_code": "TEST", "dept_name": "测试部"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_create_duplicate_dept_code(self, async_client: AsyncClient, super_admin_token: str, tech_department):
        """DEPT-010: 重复部门代码返回 409"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.post(
            "/api/admin/departments",
            json={"dept_code": tech_department.dept_code, "dept_name": "另一个技术部"},
        )

        assert response.status_code == 409
        data = response.json()
        assert data["code"] == 40900


class TestUpdateDepartment:
    """修改部门测试 - PATCH /api/admin/departments/{dept_id}"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_super_admin_update_department(self, async_client: AsyncClient, super_admin_token: str, tech_department):
        """DEPT-015: 超管修改部门名称"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.patch(
            f"/api/admin/departments/{tech_department.id}",
            json={"dept_name": "信息技术部"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_update_department_verify_change(self, async_client: AsyncClient, super_admin_token: str, tech_department):
        """DEPT-019: 修改后验证数据更新"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        new_name = "新的技术部"
        await async_client.patch(
            f"/api/admin/departments/{tech_department.id}",
            json={"dept_name": new_name},
        )

        list_resp = await async_client.get("/api/admin/departments")
        depts = list_resp.json()["data"]
        tech_dept = next(d for d in depts if d["id"] == tech_department.id)
        assert tech_dept["dept_name"] == new_name

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_update_nonexistent_department(self, async_client: AsyncClient, super_admin_token: str):
        """DEPT-017: 修改不存在的部门返回 404"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.patch(
            "/api/admin/departments/999999",
            json={"dept_name": "新名称"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == 40400

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_cannot_update_department(self, async_client: AsyncClient, dept_admin_token: str, tech_department):
        """DEPT-018: 部门管理员无权修改部门"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        response = await async_client.patch(
            f"/api/admin/departments/{tech_department.id}",
            json={"dept_name": "新名称"},
        )

        assert response.status_code == 403


class TestDeleteDepartment:
    """删除部门测试 - DELETE /api/admin/departments/{dept_id}"""

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_delete_empty_department(self, async_client: AsyncClient, super_admin_token: str, db_session):
        """DEPT-021: 删除空部门成功"""
        from tests.utils import create_department

        empty_dept = await create_department(db_session, "EMPTY", "空部门")

        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        response = await async_client.delete(f"/api/admin/departments/{empty_dept.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_delete_department_with_users(self, async_client: AsyncClient, super_admin_token: str, tech_department, multiple_employees):
        """DEPT-022: 删除有用户的部门返回 409"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.delete(f"/api/admin/departments/{tech_department.id}")

        assert response.status_code == 409
        data = response.json()
        assert data["code"] == 40901

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_delete_nonexistent_department(self, async_client: AsyncClient, super_admin_token: str):
        """DEPT-024: 删除不存在的部门返回 404"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})

        response = await async_client.delete("/api/admin/departments/999999")

        assert response.status_code == 404
        data = response.json()
        assert data["code"] == 40400

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_dept_admin_cannot_delete_department(self, async_client: AsyncClient, dept_admin_token: str, tech_department):
        """DEPT-025: 部门管理员无权删除部门"""
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})

        response = await async_client.delete(f"/api/admin/departments/{tech_department.id}")

        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.high_priority
    @pytest.mark.integration
    async def test_delete_department_verify_removed(self, async_client: AsyncClient, super_admin_token: str, db_session):
        """DEPT-026: 删除后部门不再出现在列表"""
        from tests.utils import create_department

        dept = await create_department(db_session, "TODEL", "待删除")

        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        await async_client.delete(f"/api/admin/departments/{dept.id}")

        list_resp = await async_client.get("/api/admin/departments")
        depts = list_resp.json()["data"]
        dept_ids = [d["id"] for d in depts]
        assert dept.id not in dept_ids
