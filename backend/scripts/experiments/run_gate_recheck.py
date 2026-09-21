"""快速评测：门控复核（扩组后）+ 父块展开对照数据。"""
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


async def run_once(label: str) -> dict:
    from eval.runner import run_eval
    report = await run_eval(
        user_id=1,
        user_role="employee",
        user_dept_id=1,
        skip_generation=True,
        tool_dry_run=True,
        concurrency=1,
        timeout=90.0,
        mode="fast",
        label=label,
    )
    g = report.by_group or {}
    return {
        "label": label,
        "total": report.total_cases,
        "doc_hit": report.doc_hit_rate,
        "mrr": report.mrr,
        "tool_acc": report.tool_call_accuracy,
        "distractor-topic": g.get("distractor-topic"),
        "distractor-lifecycle": g.get("distractor-lifecycle"),
        "historical": g.get("historical"),
        "multiturn": g.get("multiturn"),
        "all_groups": g,
    }


async def main() -> None:
    r1 = await run_once("gate-recheck-parent-on")
    out = BACKEND / "eval" / "gate_recheck.json"
    out.write_text(json.dumps(r1, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(r1, ensure_ascii=False, indent=2))
    print("saved", out)


if __name__ == "__main__":
    asyncio.run(main())
