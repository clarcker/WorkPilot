"""E5 三次对照：配额 on/off × 3 次（仅 retrieve，确定性 + 可见差异）。

用法：cd backend && uv run python scripts/run_quota_ab.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv

load_dotenv()

from core.config import settings  # noqa: E402
from eval.runner import load_cases  # noqa: E402
from services.embedder import get_embedding  # noqa: E402
from services.retriever import retrieve  # noqa: E402


def _rank(sources: list[dict], expected: str) -> int:
    """与 E2 一致：精确文件名优先，其次前缀（兼容带扩展名差异）。"""
    if not expected:
        return -1
    for i, s in enumerate(sources, 1):
        name = s.get("doc_name") or ""
        if name == expected:
            return i
    for i, s in enumerate(sources, 1):
        name = s.get("doc_name") or ""
        if expected.endswith(".md") and name.startswith(expected[:-3]):
            return i
        if name.endswith(".md") and expected.startswith(name[:-3]):
            return i
    return -1


async def main() -> None:
    cases = [c for c in load_cases() if (c.get("expected_doc_title") or "").strip()]
    embeds = []
    cache = Path(__file__).parent / "_embeds_cache.json"
    # 只对前 15 条有 cache；其余现算
    cached = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else []
    for i, c in enumerate(cases):
        if i < len(cached):
            embeds.append(cached[i])
        else:
            embeds.append(await get_embedding(c["question"]))
    print(f"cases={len(cases)}", flush=True)

    results = {"on": [], "off": []}
    for trial in range(3):
        for quota_on in (True, False):
            settings.retrieval_enable_fts = True
            settings.retrieval_merge_chunks = True
            settings.retrieval_must_include = quota_on
            ranks = []
            for c, vec in zip(cases, embeds):
                hits = await retrieve(
                    query_embedding=vec,
                    query_text=c["question"],
                    user_id=1,
                    user_dept_id=None,
                    user_role="super_admin",
                )
                ranks.append(_rank(hits, c["expected_doc_title"]))
            n = len(ranks)
            hit3 = sum(1 for r in ranks if 0 < r <= 3)
            rec1 = sum(1 for r in ranks if r == 1)
            mrr = sum((1.0 / r if r > 0 else 0.0) for r in ranks) / n if n else 0
            key = "on" if quota_on else "off"
            results[key].append({
                "trial": trial + 1,
                "hit3": round(hit3 / n, 4),
                "rec1": round(rec1 / n, 4),
                "mrr": round(mrr, 4),
                "ranks": ranks,
            })
            print(f"trial{trial+1} quota={key} hit3={hit3/n:.4f} mrr={mrr:.4f}", flush=True)

    def mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else 0

    on_mrrs = [r["mrr"] for r in results["on"]]
    off_mrrs = [r["mrr"] for r in results["off"]]
    same = all(
        results["on"][i]["ranks"] == results["on"][0]["ranks"]
        for i in range(3)
    ) and all(
        results["off"][i]["ranks"] == results["off"][0]["ranks"]
        for i in range(3)
    )
    print("\n=== summary ===", flush=True)
    print(f"quota ON  mrr trials={on_mrrs} mean={mean(on_mrrs)}", flush=True)
    print(f"quota OFF mrr trials={off_mrrs} mean={mean(off_mrrs)}", flush=True)
    print(f"delta mean={round(mean(on_mrrs) - mean(off_mrrs), 4)}", flush=True)
    print(f"deterministic(within-config)={same}", flush=True)
    if same:
        print(f"ranks ON ={results['on'][0]['ranks']}", flush=True)
        print(f"ranks OFF={results['off'][0]['ranks']}", flush=True)

    settings.retrieval_must_include = True


if __name__ == "__main__":
    asyncio.run(main())
