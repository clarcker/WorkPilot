"""混合检索冒烟：纯向量 vs RRF（向量+关键词）。

用法：cd backend && uv run python scripts/smoke_hybrid.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv

load_dotenv()

from core.config import settings  # noqa: E402
from services.embedder import get_embedding  # noqa: E402
from services.retriever import retrieve  # noqa: E402

QUERIES = [
    ("语义类", "出差住宿报销标准是多少？"),
    ("关键词/编号", "第 3.2 条说了什么"),
    ("关键词/编号", "TR-2026-0091 是什么单"),
    ("专有名词", "nomic-embed-text 是哪个模型"),
]


async def main() -> None:
    # 用超管身份，排除权限干扰
    user_id, role, dept = 1, "super_admin", None
    # 若 id=1 不存在，用 seed 的 admin
    from sqlalchemy import text
    from db.session import async_session_factory
    async with async_session_factory() as db:
        uid = await db.scalar(text("SELECT id FROM users WHERE username='admin'"))
        if uid:
            user_id = int(uid)

    print(f"user_id={user_id} role={role}")
    print(f"fts_enabled={settings.retrieval_enable_fts} top_k={settings.retrieval_top_k}")

    for label, q in QUERIES:
        vec = await get_embedding(q)

        # A: 纯向量（关 FTS）
        settings.retrieval_enable_fts = False
        t0 = time.time()
        vec_only = await retrieve(
            query_embedding=vec, query_text="",
            user_id=user_id, user_dept_id=dept, user_role=role,
        )
        t_vec = (time.time() - t0) * 1000

        # B: 混合 RRF
        settings.retrieval_enable_fts = True
        t0 = time.time()
        hybrid = await retrieve(
            query_embedding=vec, query_text=q,
            user_id=user_id, user_dept_id=dept, user_role=role,
        )
        t_hyb = (time.time() - t0) * 1000

        v_docs = [c["doc_name"] for c in vec_only[:3]]
        h_docs = [c["doc_name"] for c in hybrid[:3]]
        print(f"\n[{label}] {q}")
        print(f"  纯向量 ({len(vec_only)}条 {t_vec:.0f}ms): {v_docs}")
        print(f"  混合RRF ({len(hybrid)}条 {t_hyb:.0f}ms): {h_docs}")
        extra = [d for d in h_docs if d not in v_docs]
        if extra:
            print(f"  RRF 额外命中: {extra}")

    settings.retrieval_enable_fts = True


if __name__ == "__main__":
    asyncio.run(main())
