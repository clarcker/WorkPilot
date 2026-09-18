"""
场景 D 演示：同题不同答（权限过滤）

同一问题「薪酬调整实施方案里写了什么 / 研发提测流程」：
- 客服部员工 zhaoliu：应看不到薪酬文档 → 回答「未找到」且不透露存在
- 研发员工 zhangsan：薪酬在 specific_users 白名单 → 可能召回
- 超管 admin：可见全部 ready 文档

用法：
    cd backend
    uv run python scripts/demo_permission_diff.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

import httpx  # noqa: E402

BASE = os.getenv("DEMO_BASE", "http://localhost:8000")
PASSWORD = os.getenv("DEMO_PWD", "Demo@12345")
QUESTION = "薪酬调整实施方案里写了什么？"


def login(username: str, password: str) -> str | None:
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    if r.status_code != 200:
        print(f"  login {username} FAILED {r.status_code} {r.text[:120]}")
        return None
    data = r.json().get("data") or {}
    return data.get("access_token")


def ask(token: str, question: str) -> dict:
    t0 = time.time()
    resp = httpx.post(
        f"{BASE}/api/chat/stream",
        json={"query": question},
        headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
        timeout=180,
    )
    tokens, sources = [], []
    for line in resp.text.splitlines():
        if not line.startswith("data: "):
            continue
        import json

        ev = json.loads(line[6:])
        t = ev.get("type")
        if t == "token":
            tokens.append(ev.get("content") or "")
        elif t == "sources":
            sources = ev.get("content") or []
    answer = "".join(tokens)
    docs = [s.get("doc_name") for s in sources]
    leaked = any("薪酬" in str(d) for d in docs)
    print(f"  elapsed={time.time()-t0:.0f}s sources={docs}")
    print(f"  answer: {answer[:220].replace(chr(10), ' ')}")
    print(f"  含薪酬文档引用: {leaked}")
    return {"answer": answer, "docs": docs, "leaked": leaked}


async def main() -> None:
    print(f"问题: {QUESTION}\n")

    print("[1] 客服部员工 zhaoliu（白名单外，期望不泄漏薪酬文档）")
    tok = login("zhaoliu", PASSWORD)
    if tok:
        ask(tok, QUESTION)

    print("\n[2] 研发员工 zhangsan（specific_users 白名单内）")
    tok = login("zhangsan", PASSWORD)
    if tok:
        ask(tok, QUESTION)

    print("\n[3] 超管 admin（可见全部）")
    tok = login("admin", os.getenv("ADMIN_PWD", "Admin@123456"))
    if tok:
        ask(tok, QUESTION)

    print("\n演示要点：无权文档不参与召回，也不在回答中透露其存在（不说「你无权限看 X」）。")


if __name__ == "__main__":
    asyncio.run(main())
