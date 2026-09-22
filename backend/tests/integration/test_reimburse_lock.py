"""报销 confirm 并发：双击不得双扣额度。"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select


class TestConfirmConcurrency:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_double_confirm_deducts_limit_once(
        self,
        db_session,
        async_client,
        employee_token: str,
        employee_user,
    ):
        from db.models import ReimbursementLimit, ReimbursementRequest
        from api.reimbursements import confirm_request  # noqa: F401
        from core.deps import get_active_user

        # 直接插 draft + limit，避免走完整工具链
        limit = ReimbursementLimit(
            user_id=employee_user.id,
            category="差旅住宿",
            annual_max=10000,
            used=0,
        )
        db_session.add(limit)
        draft = ReimbursementRequest(
            request_no="RB-TEST-LOCK-0001",
            user_id=employee_user.id,
            dept_id=employee_user.dept_id,
            category="差旅住宿",
            amount=2000,
            status="draft",
            idempotency_key="test-lock-0001",
        )
        db_session.add(draft)
        await db_session.commit()
        rid = draft.id
        uid = employee_user.id

        # 两个独立 session 并发 confirm（模拟双击）
        from db.session import async_session_factory
        from api import reimbursements as rb

        class _User:
            id = uid
            real_name = "t"
            role = "employee"

        async def _once():
            async with async_session_factory() as session:
                class Req:
                    headers = {}
                    class client:
                        host = "127.0.0.1"
                return await rb.confirm_request(
                    rid, Req(), current_user=_User(), db=session  # type: ignore[arg-type]
                )

        results = await asyncio.gather(_once(), _once(), return_exceptions=True)
        ok = [r for r in results if not isinstance(r, Exception)]
        assert len(ok) >= 1

        async with async_session_factory() as session:
            lim = await session.scalar(
                select(ReimbursementLimit).where(ReimbursementLimit.user_id == uid)
            )
            row = await session.scalar(
                select(ReimbursementRequest).where(ReimbursementRequest.id == rid)
            )
            assert row.status == "pending"
            # 只扣一次 2000，不是 4000
            assert lim.used == 2000
