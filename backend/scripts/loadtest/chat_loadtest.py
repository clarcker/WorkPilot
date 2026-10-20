"""P3：简易压测（无第三方依赖）。登录 → 流式提问，统计 TTFT/P95。

用法：
  cd backend
  uv run python scripts/loadtest/chat_loadtest.py --base http://127.0.0.1:8000 \
    --user zhangsan --password Demo@12345 --concurrency 1 --duration 120
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx

QUESTIONS = [
    "公司规定的住宿报销标准是什么？",
    "请假需要提前几天申请？",
    "出差补贴怎么算？",
    "公司的安全合规制度是什么？",
    "设备维修怎么申请？",
    "新员工入职需要做什么？",
    "年假有几天？",
    "病假需要提供什么证明？",
    "通讯补贴标准是什么？",
    "加班调休怎么算？",
    "会议室怎么预约？",
    "信息安全有哪些基本要求？",
    "现在出差住宿标准是多少？",
    "一线城市住宿报销上限是多少？",
    "迟到超过 2 小时怎么处理？",
    "设备遗失怎么赔偿？",
    "入职第一天要找谁？",
    "差旅住宿标准能上浮吗？",
    "报销制度里住宿上限是多少？",
    "考勤规则里年假顺延怎么规定？",
]


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


async def login(client: httpx.AsyncClient, user: str, password: str) -> str:
    r = await client.post("/api/auth/login", json={"username": user, "password": password})
    r.raise_for_status()
    body = r.json()
    return body.get("data", {}).get("access_token") or body.get("access_token")


async def one_stream(client: httpx.AsyncClient, token: str, q: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    t0 = time.perf_counter()
    ttft = None
    queued = False
    err = None
    done_at = None
    try:
        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={"query": q},
            headers=headers,
            timeout=httpx.Timeout(30.0, read=180.0),
        ) as resp:
            if resp.status_code != 200:
                err = f"http_{resp.status_code}"
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    ev = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                et = ev.get("type")
                if et == "queued":
                    queued = True
                elif et == "token" and ttft is None:
                    ttft = time.perf_counter() - t0
                elif et in ("done", "error"):
                    if et == "error":
                        err = str(ev.get("content") or "error")[:80]
                    done_at = time.perf_counter() - t0
                    break
    except Exception as exc:
        err = type(exc).__name__
        done_at = time.perf_counter() - t0
    if done_at is None:
        done_at = time.perf_counter() - t0
    return {"ttft": ttft, "total": done_at, "queued": queued, "error": err}


async def worker(client, token, duration, results: list, q_idx: list):
    end = time.time() + duration
    while time.time() < end:
        q = QUESTIONS[q_idx[0] % len(QUESTIONS)]
        q_idx[0] += 1
        r = await one_stream(client, token, q)
        results.append(r)
        await asyncio.sleep(0.2)


async def run(args) -> dict:
    async with httpx.AsyncClient(base_url=args.base) as client:
        token = await login(client, args.user, args.password)
        results: list = []
        q_idx = [0]
        start = time.perf_counter()
        tasks = [
            asyncio.create_task(worker(client, token, args.duration, results, q_idx))
            for _ in range(args.concurrency)
        ]
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start

    ttfts = [r["ttft"] for r in results if r.get("ttft") is not None]
    totals = [r["total"] for r in results if r.get("total") is not None]
    errors = [r for r in results if r.get("error")]
    queued_n = sum(1 for r in results if r.get("queued"))
    summary = {
        "base": args.base,
        "concurrency": args.concurrency,
        "duration_s": args.duration,
        "requests": len(results),
        "rps": round(len(results) / elapsed, 3) if elapsed else 0,
        "error_rate": round(len(errors) / len(results), 4) if results else 0,
        "queued_ratio": round(queued_n / len(results), 4) if results else 0,
        "ttft_p50": round(pct(ttfts, 50), 3),
        "ttft_p95": round(pct(ttfts, 95), 3),
        "total_p50": round(pct(totals, 50), 3),
        "total_p95": round(pct(totals, 95), 3),
        "sample_errors": [e.get("error") for e in errors[:5]],
    }
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--user", default="zhangsan")
    p.add_argument("--password", default="Demo@12345")
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--out", default="")
    args = p.parse_args()
    summary = asyncio.run(run(args))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(existing, list):
            existing = [existing]
        existing.append(summary)
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
