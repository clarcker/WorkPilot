"""P6：检索层 eval（fixture embedding，CI 可离线跑）。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv
load_dotenv(BACKEND / ".env")

FIXTURE = BACKEND / "eval" / "fixtures" / "query_embeddings.json"
BASELINE = BACKEND / "eval" / "baseline.json"


async def main() -> None:
    from services.retriever import retrieve
    from core.config import settings
    from eval.runner import load_cases

    if not FIXTURE.exists():
        print(f"[skip] fixture 不存在: {FIXTURE}")
        print("请在本地 Ollama 可用时运行 scripts/experiments/build_eval_fixtures.py")
        sys.exit(0)

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    model = data.get("model_name") or settings.ollama_embed_model
    cases_map = {c["id"]: c for c in load_cases() if (c.get("expected_doc_title") or "").strip()}
    embeds = data.get("cases") or {}

    ranks = []
    for cid, vec in embeds.items():
        c = cases_map.get(cid)
        if not c:
            continue
        hits = await retrieve(
            query_embedding=vec,
            query_text=c["question"],
            user_id=1,
            user_dept_id=None,
            user_role="super_admin",
            time_scope=c.get("time_scope") or (
                "historical" if c.get("group") == "historical" else "current"
            ),
        )
        expected = c["expected_doc_title"]
        rank = -1
        for i, h in enumerate(hits, 1):
            name = h.get("doc_name") or ""
            if name == expected or (expected.endswith(".md") and name.startswith(expected[:-3])):
                rank = i
                break
        ranks.append(rank)

    n = len(ranks)
    mrr = sum((1.0 / r if r > 0 else 0.0) for r in ranks) / n if n else 0.0
    hit3 = sum(1 for r in ranks if 0 < r <= 3) / n if n else 0.0
    result = {
        "model": model,
        "cases": n,
        "mrr": round(mrr, 4),
        "doc_hit_at_3": round(hit3, 4),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    baseline = {"mrr": 0.60, "doc_hit_at_3": 0.80}
    if BASELINE.exists():
        baseline.update(json.loads(BASELINE.read_text(encoding="utf-8")))
    threshold = float(baseline.get("mrr", 0.60)) - 0.02
    print(f"baseline.mrr={baseline.get('mrr')} threshold={threshold}")
    if n >= 5 and mrr < threshold:
        print(f"FAIL: mrr {mrr:.4f} < {threshold:.4f}")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    asyncio.run(main())
