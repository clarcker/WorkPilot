"""
E4 检索策略对照：只调 retrieve()，不走 LLM / query_understand。

指标：期望文档的 rank / doc_hit@3 / recall@1 / mrr
用法：cd backend && uv run python scripts/run_eval_matrix.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv

load_dotenv()

from core.config import settings  # noqa: E402
from eval.runner import load_cases  # noqa: E402
from services.embedder import get_embedding  # noqa: E402
from services.retriever import retrieve  # noqa: E402

CONFIGS = [
    ("纯向量", False, False, False),
    ("向量+merge", False, False, True),
    ("混合RRF", True, False, True),
    ("混合+must", True, True, True),
]


def _match_rank(sources: list[dict], expected: str) -> int:
    if not expected:
        return -1
    for i, s in enumerate(sources, 1):
        name = s.get("doc_name") or ""
        if name == expected or expected in name:
            return i
    return -1


async def main() -> None:
    all_cases = load_cases()
    cases = [
        c for c in all_cases
        if (c.get("expected_doc_title") or "").strip()
    ][:15]  # 对照子集，完整表可再扩
    print(f"doc cases: {len(cases)}", flush=True)
    print(f"top_k={settings.retrieval_top_k} min_score={settings.retrieval_min_score}", flush=True)

    embeds = []
    cache = Path(__file__).parent / "_embeds_cache.json"
    if cache.exists():
        embeds = json.loads(cache.read_text(encoding="utf-8"))
        print(f"loaded embeddings cache: {len(embeds)}", flush=True)
        cases = cases[: len(embeds)]
    else:
        for i, c in enumerate(cases):
            embeds.append(await get_embedding(c["question"]))
            if (i + 1) % 5 == 0:
                print(f"  embed {i+1}/{len(cases)}", flush=True)

    rows = []
    for label, fts, must, merge in CONFIGS:
        settings.retrieval_enable_fts = fts
        settings.retrieval_must_include = must
        settings.retrieval_merge_chunks = merge
        print(f"\n>>> {label} fts={fts} must={must} merge={merge}", flush=True)
        t0 = time.time()
        ranks = []
        for c, vec in zip(cases, embeds):
            hits = await retrieve(
                query_embedding=vec,
                query_text=c["question"],
                user_id=1,
                user_dept_id=None,
                user_role="super_admin",
            )
            ranks.append(_match_rank(hits, c["expected_doc_title"]))
        n = len(ranks)
        hit3 = sum(1 for r in ranks if 0 < r <= 3)
        rec1 = sum(1 for r in ranks if r == 1)
        mrr = sum((1.0 / r if r > 0 else 0.0) for r in ranks) / n if n else 0
        row = {
            "label": label,
            "doc_hit@3": round(hit3 / n, 4) if n else 0,
            "recall@1": round(rec1 / n, 4) if n else 0,
            "mrr": round(mrr, 4),
            "miss": sum(1 for r in ranks if r < 0),
            "wall_s": round(time.time() - t0, 1),
        }
        rows.append(row)
        print(f"    {row}", flush=True)

    settings.retrieval_enable_fts = True
    settings.retrieval_must_include = True
    settings.retrieval_merge_chunks = True

    print("\n| 配置 | doc_hit@3 | recall@1 | mrr | miss |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['label']} | {r['doc_hit@3']} | {r['recall@1']} | {r['mrr']} | {r['miss']} |"
        )


if __name__ == "__main__":
    asyncio.run(main())
