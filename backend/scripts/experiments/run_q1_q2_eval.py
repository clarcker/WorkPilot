"""Run eval offline and print Q1/Q2 acceptance metrics."""
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
    from eval.runner import run_eval

    report = await run_eval(
        user_id=1,
        user_role="employee",
        user_dept_id=1,
        skip_generation=True,
        tool_dry_run=True,
        concurrency=1,
        timeout=90.0,
    )

    groups = report.by_group or {}
    out = {
        "total_cases": report.total_cases,
        "scored_cases": report.scored_cases,
        "timeout_count": report.timeout_count,
        "intent_accuracy": report.intent_accuracy,
        "doc_hit_rate": report.doc_hit_rate,
        "mrr": report.mrr,
        "heading_hit_rate": report.heading_hit_rate,
        "tool_call_accuracy": report.tool_call_accuracy,
        "citation_rate": report.citation_rate,
        "permission_pass_rate": report.permission_pass_rate,
        "avg_latency_ms": report.avg_latency_ms,
        "by_group": groups,
        "failed_count": len(report.failed_cases or []),
        "failed_cases": (report.failed_cases or [])[:20],
    }

    # group focus
    focus = {}
    for g in [
        "distractor-lifecycle",
        "distractor-topic",
        "historical",
        "multiturn",
        "permission",
        "tool",
        "policy",
    ]:
        if g in groups:
            focus[g] = groups[g]
    out["focus_groups"] = focus

    # multiturn tool-only accuracy among session_tool_calls cases
    mt = [r for r in report.case_results if r.group == "multiturn"]
    if mt:
        out["multiturn_detail"] = {
            "count": len(mt),
            "tool_ok": sum(1 for r in mt if r.tool_call_correct),
            "intent_ok": sum(1 for r in mt if r.intent_correct),
        }

    hist = [r for r in report.case_results if r.group == "historical"]
    if hist:
        out["historical_detail"] = {
            "count": len(hist),
            "doc_hit": sum(1 for r in hist if r.doc_hit),
            "avg_mrr": round(sum(r.mrr for r in hist) / len(hist), 4),
        }

    draft_leaks = [r for r in report.case_results if r.forbidden_doc_leaked]
    out["forbidden_leaks"] = [
        {"case_id": r.case_id, "question": r.question, "detail": r.detail}
        for r in draft_leaks
    ]

    out_path = BACKEND / "eval" / "q1_q2_run.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n[saved] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
