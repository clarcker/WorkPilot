"""Eval API — 运行评测并返回结果。"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from core.deps import require_super_admin
from db.models import EvalRun, User
from eval.runner import DEFAULT_CASE_TIMEOUT, EvalReport, run_eval
from schemas.common import BaseResp

router = APIRouter()


def _report_payload(report: EvalReport, skip_generation: bool, tool_dry_run: bool) -> dict:
    payload = {
        "total_cases": report.total_cases,
        "scored_cases": report.scored_cases,
        "timeout_count": report.timeout_count,
        "intent_accuracy": report.intent_accuracy,
        "doc_hit_rate": report.doc_hit_rate,
        "doc_hit_at_3": report.doc_hit_rate,
        "recall_at_1": report.recall_at_1,
        "mrr": report.mrr,
        "heading_hit_rate": report.heading_hit_rate,
        "tool_call_accuracy": report.tool_call_accuracy,
        "citation_rate": report.citation_rate,
        "permission_pass_rate": report.permission_pass_rate,
        "avg_latency_ms": report.avg_latency_ms,
        "by_group": report.by_group,
        "failed_cases": report.failed_cases,
        "timeout_cases": report.timeout_cases,
        "skip_generation": skip_generation,
        "tool_dry_run": tool_dry_run,
        "mode": report.mode,
        "judge_model": report.judge_model,
        "faithfulness_avg": report.faithfulness_avg,
        "points_coverage": report.points_coverage,
        "hallucination_count": report.hallucination_count,
        "refusal_correct_rate": report.refusal_correct_rate,
        "local_judge": report.local_judge,
        "note": (
            "本地裁判，可信度低"
            if report.local_judge and report.mode == "judge"
            else "skip_generation=true 时 citation_rate 仅基于 sources 列表，未评估答案正文"
        ),
        "case_results": [
            {
                "case_id": c.case_id,
                "question": c.question,
                "group": c.group,
                "intent_correct": c.intent_correct,
                "doc_hit": c.doc_hit,
                "doc_rank": c.doc_rank,
                "recall_at_1": c.recall_at_1,
                "mrr": c.mrr,
                "heading_hit": c.heading_hit,
                "tool_call_correct": c.tool_call_correct,
                "has_citation": c.has_citation,
                "forbidden_doc_leaked": c.forbidden_doc_leaked,
                "latency_ms": c.latency_ms,
                "timed_out": c.timed_out,
                "detail": c.detail,
                "judge": c.judge,
                "answer_preview": (c.answer or "")[:300],
            }
            for c in report.case_results
        ],
    }
    return payload


async def _persist_run(
    report: EvalReport,
    payload: dict,
    *,
    skip_generation: bool,
    tool_dry_run: bool,
    operator_id: int | None,
    label: str | None = None,
    status: str = "finished",
    progress: int | None = None,
    run_id: int | None = None,
) -> Optional[int]:
    from datetime import datetime, timezone
    from db.session import async_session_factory

    async with async_session_factory() as db:
        if run_id is not None:
            row = await db.get(EvalRun, run_id)
            if not row:
                return run_id
        else:
            row = EvalRun()
            db.add(row)
        row.finished_at = datetime.now(timezone.utc)
        row.total_cases = payload["total_cases"]
        row.scored_cases = payload["scored_cases"]
        row.timeout_count = payload["timeout_count"]
        row.intent_accuracy = payload["intent_accuracy"]
        row.doc_hit_rate = payload["doc_hit_rate"]
        row.recall_at_1 = payload.get("recall_at_1")
        row.mrr = payload.get("mrr")
        row.heading_hit_rate = payload.get("heading_hit_rate")
        row.tool_call_accuracy = payload["tool_call_accuracy"]
        row.citation_rate = payload["citation_rate"]
        row.permission_pass_rate = payload["permission_pass_rate"]
        row.avg_latency_ms = payload["avg_latency_ms"]
        row.skip_generation = skip_generation
        row.tool_dry_run = tool_dry_run
        row.case_results = payload["case_results"]
        row.failed_cases = payload["failed_cases"]
        row.operator_id = operator_id
        row.note = payload.get("note")
        row.judge_model = payload.get("judge_model")
        row.faithfulness_avg = payload.get("faithfulness_avg")
        row.points_coverage = payload.get("points_coverage")
        row.hallucination_count = payload.get("hallucination_count")
        row.refusal_correct_rate = payload.get("refusal_correct_rate")
        row.label = label
        row.mode = payload.get("mode") or "fast"
        row.status = status
        row.progress = progress if progress is not None else payload["total_cases"]
        try:
            from services.prompt_loader import current_prompt_set
            row.prompt_set_version = current_prompt_set()
        except Exception:
            pass
        await db.commit()
        return int(row.id)


async def _create_pending_run(
    operator_id: int | None,
    mode: str,
    label: str | None,
    total_estimate: int,
) -> int:
    from db.session import async_session_factory
    async with async_session_factory() as db:
        row = EvalRun(
            total_cases=total_estimate,
            scored_cases=0,
            skip_generation=(mode != "judge"),
            tool_dry_run=True,
            operator_id=operator_id,
            label=label,
            mode=mode,
            status="running",
            progress=0,
            note="后台运行中" if mode == "judge" else None,
        )
        db.add(row)
        await db.commit()
        return int(row.id)


async def _run_eval_background(
    run_id: int,
    operator_id: int | None,
    user_id: int,
    user_role: str,
    user_dept_id: int | None,
    mode: str,
    skip_generation: bool,
    tool_dry_run: bool,
    concurrency: int,
    timeout: float,
    label: str | None,
) -> None:
    from db.session import async_session_factory

    async def progress_cb(done: int, total: int) -> None:
        try:
            async with async_session_factory() as db:
                row = await db.get(EvalRun, run_id)
                if row:
                    row.progress = done
                    row.total_cases = total
                    row.status = "running"
                    await db.commit()
        except Exception:
            pass

    try:
        report = await run_eval(
            user_id=user_id,
            user_role=user_role,
            user_dept_id=user_dept_id,
            skip_generation=skip_generation,
            tool_dry_run=tool_dry_run,
            concurrency=concurrency,
            timeout=timeout,
            mode=mode,
            label=label,
            operator_id=operator_id,
            progress_cb=progress_cb,
        )
        payload = _report_payload(report, skip_generation=skip_generation, tool_dry_run=tool_dry_run)
        await _persist_run(
            report, payload,
            skip_generation=skip_generation,
            tool_dry_run=tool_dry_run,
            operator_id=operator_id,
            label=label,
            status="finished",
            progress=payload["total_cases"],
            run_id=run_id,
        )
    except Exception as exc:
        from datetime import datetime, timezone
        async with async_session_factory() as db:
            row = await db.get(EvalRun, run_id)
            if row:
                row.status = "failed"
                row.finished_at = datetime.now(timezone.utc)
                row.note = f"eval failed: {type(exc).__name__}: {exc}"
                await db.commit()


@router.post("/run", response_model=BaseResp[dict])
async def run_evaluation(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_super_admin),
    mode: str = Query("fast", pattern="^(fast|judge)$", description="fast=检索/工具；judge=生成+LLM-as-judge"),
    label: Optional[str] = Query(None, max_length=100),
    skip_generation: bool = Query(
        True,
        description="跳过答案生成节点。judge 模式强制生成，此参数忽略",
    ),
    tool_dry_run: bool = Query(
        True, description="工具演练模式：照常校验权限与参数，但不写库",
    ),
    concurrency: int = Query(
        1, ge=1, le=4,
        description="并发条数。judge 模式建议 1，避免裁判与生成争抢",
    ),
    timeout: float = Query(
        DEFAULT_CASE_TIMEOUT, ge=10, le=600, description="单条 case 墙钟上限（秒）",
    ),
):
    if mode == "judge":
        skip_generation = False
        concurrency = min(concurrency, 2)
        # 预估 judge case 数
        from eval.runner import load_cases_from_db
        all_cases = await load_cases_from_db()
        n_judge = sum(1 for c in all_cases if c.get("judge"))
        run_id = await _create_pending_run(
            operator_id=current_user.id,
            mode="judge",
            label=label,
            total_estimate=n_judge,
        )
        background_tasks.add_task(
            _run_eval_background,
            run_id,
            current_user.id,
            current_user.id,
            current_user.role.value,
            current_user.dept_id,
            "judge",
            False,
            tool_dry_run,
            concurrency,
            timeout,
            label,
        )
        return BaseResp.ok(
            {"run_id": run_id, "mode": "judge", "status": "running", "total_estimate": n_judge},
            message="judge 评测已启动，稍后 GET /api/quality/runs/{run_id} 查看进度",
        )

    report = await run_eval(
        user_id=current_user.id,
        user_role=current_user.role.value,
        user_dept_id=current_user.dept_id,
        skip_generation=skip_generation,
        tool_dry_run=tool_dry_run,
        concurrency=concurrency,
        timeout=timeout,
        mode=mode,
        label=label,
        operator_id=current_user.id,
    )
    payload = _report_payload(report, skip_generation=skip_generation, tool_dry_run=tool_dry_run)
    try:
        run_id = await _persist_run(
            report, payload,
            skip_generation=skip_generation,
            tool_dry_run=tool_dry_run,
            operator_id=current_user.id,
            label=label,
        )
        payload["run_id"] = run_id
    except Exception:
        pass  # 落库失败不影响评测返回

    return BaseResp.ok(payload)
