"""生成 CI 检索层 fixture：把 case 的 query embedding 与模型名写入 eval/fixtures/。"""
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


async def main() -> None:
    from core.config import settings
    from eval.runner import load_cases
    from services.embedder import get_embedding

    cases = [c for c in load_cases() if (c.get("expected_doc_title") or "").strip()]
    out = {"model_name": settings.ollama_embed_model, "cases": {}}
    for c in cases:
        vec = await get_embedding(c["question"])
        out["cases"][c["id"]] = vec
        print(c["id"], "ok")
    dest = BACKEND / "eval" / "fixtures" / "query_embeddings.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out), encoding="utf-8")
    print("saved", dest, "n=", len(out["cases"]))

    baseline = BACKEND / "eval" / "baseline.json"
    if not baseline.exists():
        baseline.write_text(json.dumps({"mrr": 0.60, "doc_hit_at_3": 0.80}, indent=2), encoding="utf-8")
        print("wrote default baseline")


if __name__ == "__main__":
    asyncio.run(main())
