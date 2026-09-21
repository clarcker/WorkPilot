"""Q3 judge 基线运行脚本。"""
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
    from eval.runner import run_eval, seed_eval_cases_from_json

    await seed_eval_cases_from_json()

    report = await run_eval(
        user_id=1,
        user_role="employee",
        user_dept_id=1,
        skip_generation=False,
        tool_dry_run=True,
        concurrency=1,
        timeout=180.0,
        mode="judge",
        label="Q3-judge-baseline",
        operator_id=1,
    )

    out = {
        "mode": report.mode,
        "total_cases": report.total_cases,
        "scored_cases": report.scored_cases,
        "timeout_count": report.timeout_count,
        "intent_accuracy": report.intent_accuracy,
        "doc_hit_rate": report.doc_hit_rate,
        "mrr": report.mrr,
        "tool_call_accuracy": report.tool_call_accuracy,
        "citation_rate": report.citation_rate,
        "judge_model": report.judge_model,
        "local_judge": report.local_judge,
        "faithfulness_avg": report.faithfulness_avg,
        "points_coverage": report.points_coverage,
        "hallucination_count": report.hallucination_count,
        "refusal_correct_rate": report.refusal_correct_rate,
        "cases": [
            {
                "case_id": c.case_id,
                "group": c.group,
                "question": c.question,
                "answer_preview": (c.answer or "")[:200],
                "judge": c.judge,
            }
            for c in report.case_results
        ],
    }
    path = BACKEND / "eval" / "q3_judge_baseline.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "cases"}, ensure_ascii=False, indent=2))
    print("\n--- per-case ---")
    for c in out["cases"]:
        j = c.get("judge") or {}
        print(
            f"{c['case_id']} [{c['group']}] faith={j.get('faithfulness')} "
            f"points={j.get('points_covered')} hallu={j.get('hallucinated_claims')} "
            f"cite={j.get('citation_correct')} err={j.get('error')}"
        )
    print(f"\n[saved] {path}")

    # 落库
    try:
        from api.eval import _persist_run, _report_payload
        payload = _report_payload(report, skip_generation=False, tool_dry_run=True)
        run_id = await _persist_run(
            report, payload,
            skip_generation=False,
            tool_dry_run=True,
            operator_id=1,
            label="Q3-judge-baseline",
        )
        print(f"[eval_runs] id={run_id}")
    except Exception as exc:
        print(f"[warn] persist failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
