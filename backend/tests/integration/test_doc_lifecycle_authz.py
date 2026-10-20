"""Q1 权限：supersedes / lifecycle 不得跨部门下架文档。"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from io import BytesIO


class TestSupersedesPermission:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_dept_admin_cannot_supersede_global_doc(
        self, async_client: AsyncClient, dept_admin_token: str,
        super_admin_token: str, mock_file_storage, tech_department,
    ):
        """dept_admin 不能把 global 文档标成 superseded（跨部门/全体下架）。"""
        # 超管上传一份 global 文档
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        md = b"# Global Policy\n\nAll-hands rule."
        files = {"file": ("global_policy.md", BytesIO(md), "text/markdown")}
        resp = await async_client.post(
            "/api/docs/upload",
            files=files,
            data={"dept_id": str(tech_department.id), "visibility": "global"},
        )
        assert resp.status_code == 201
        global_doc_id = resp.json()["data"]["id"]

        # dept_admin 尝试用 supersedes_doc_id 上传
        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})
        files2 = {"file": ("my_new.md", BytesIO(b"# New\n\nx"), "text/markdown")}
        resp2 = await async_client.post(
            "/api/docs/upload",
            files=files2,
            data={
                "visibility": "dept_only",
                "supersedes_doc_id": str(global_doc_id),
            },
        )
        assert resp2.status_code == 403
        detail = resp2.json()["detail"]
        code = detail["code"] if isinstance(detail, dict) else None
        assert code in (40302, 40303)

        # 旧文档 lifecycle 仍为 effective
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        get = await async_client.get(f"/api/docs/{global_doc_id}")
        assert get.status_code == 200
        assert get.json()["data"]["lifecycle"] == "effective"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_dept_admin_cannot_supersede_other_dept(
        self, async_client: AsyncClient, dept_admin_token: str,
        super_admin_token: str, mock_file_storage, tech_department, hr_department,
    ):
        """dept_admin 不能替代其他部门文档。"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        files = {
            "file": (
                "hr_policy.md",
                BytesIO(b"# HR Policy\n\nInternal."),
                "text/markdown",
            )
        }
        resp = await async_client.post(
            "/api/docs/upload",
            files=files,
            data={"dept_id": str(hr_department.id), "visibility": "dept_only"},
        )
        assert resp.status_code == 201
        hr_doc_id = resp.json()["data"]["id"]

        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})
        files2 = {"file": ("rd_new.md", BytesIO(b"# RD\n\nx"), "text/markdown")}
        resp2 = await async_client.post(
            "/api/docs/upload",
            files=files2,
            data={
                "visibility": "dept_only",
                "supersedes_doc_id": str(hr_doc_id),
            },
        )
        assert resp2.status_code == 403
        detail = resp2.json()["detail"]
        code = detail["code"] if isinstance(detail, dict) else None
        assert code == 40302

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_dept_admin_cannot_patch_global_to_superseded(
        self, async_client: AsyncClient, dept_admin_token: str,
        super_admin_token: str, mock_file_storage, tech_department,
    ):
        """PATCH lifecycle 不得由 dept_admin 把 global 文档改为 superseded。"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        files = {
            "file": (
                "global2.md",
                BytesIO(b"# G2\n\nbody"),
                "text/markdown",
            )
        }
        resp = await async_client.post(
            "/api/docs/upload",
            files=files,
            data={"dept_id": str(tech_department.id), "visibility": "global"},
        )
        doc_id = resp.json()["data"]["id"]

        async_client.headers.update({"Authorization": f"Bearer {dept_admin_token}"})
        patch = await async_client.patch(
            f"/api/docs/{doc_id}", json={"lifecycle": "superseded"}
        )
        # 可能因部门范围先 40301，或 40303——均须拒绝
        assert patch.status_code == 403

        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        get = await async_client.get(f"/api/docs/{doc_id}")
        assert get.json()["data"]["lifecycle"] == "effective"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_super_admin_can_supersede_same_chain(
        self, async_client: AsyncClient, super_admin_token: str,
        mock_file_storage, tech_department,
    ):
        """超管可建立版本链：新文档替代旧文档，旧文档 lifecycle→superseded。"""
        async_client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
        old = await async_client.post(
            "/api/docs/upload",
            files={"file": ("old_v1.md", BytesIO(b"# V1\n\nold"), "text/markdown")},
            data={"dept_id": str(tech_department.id), "visibility": "dept_only"},
        )
        old_id = old.json()["data"]["id"]
        new = await async_client.post(
            "/api/docs/upload",
            files={"file": ("new_v2.md", BytesIO(b"# V2\n\nnew"), "text/markdown")},
            data={
                "dept_id": str(tech_department.id),
                "visibility": "dept_only",
                "lifecycle": "effective",
                "supersedes_doc_id": str(old_id),
                "effective_date": "2026-01-01",
            },
        )
        assert new.status_code == 201
        assert new.json()["data"]["supersedes_doc_id"] == old_id

        old_get = await async_client.get(f"/api/docs/{old_id}")
        assert old_get.json()["data"]["lifecycle"] == "superseded"
