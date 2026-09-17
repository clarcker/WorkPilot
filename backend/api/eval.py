"""Eval API — 运行评测并返回结果。"""
from fastapi import APIRouter, Depends, Query
from core.deps import require_super_admin
from db.models import User
from eval.runner import DEFAULT_CASE_TIMEOUT, run_eval
from schemas.common import BaseResp

router = APIRouter()


@router.post("/run", response_model=BaseResp[dict])
async def run_evaluation(
    current_user: User = Depends(require_super_admin),
    skip_generation: bool = Query(
        True,
        description="跳过答案生成节点。四个指标都不依赖答案正文，"
                    "而生成是最慢的一步；关掉可做端到端验证，但需同时调大 timeout",
    ),
    tool_dry_run: bool = Query(
        True, description="工具演练模式：照常校验权限与参数，但不写库",
    ),
    concurrency: int = Query(
        1, ge=1, le=8,
        description="并发条数。>1 时 avg_latency_ms 会受相互争抢影响",
    ),
    timeout: float = Query(
        DEFAULT_CASE_TIMEOUT, ge=10, le=600, description="单条 case 墙钟上限（秒）",
    ),
):
    report = await run_eval(
        user_id=current_user.id,
        user_role=current_user.role.value,
        user_dept_id=current_user.dept_id,
        skip_generation=skip_generation,
        tool_dry_run=tool_dry_run,
        concurrency=concurrency,
        timeout=timeout,
    )
    payload = {
        "total_cases": report.total_cases,
        "scored_cases": report.scored_cases,
        "timeout_count": report.timeout_count,
        "intent_accuracy": report.intent_accuracy,
        "doc_hit_rate": report.doc_hit_rate,
        "tool_call_accuracy": report.tool_call_accuracy,
        "citation_rate": report.citation_rate,
        "permission_pass_rate": report.permission_pass_rate,
        "avg_latency_ms": report.avg_latency_ms,
        "failed_cases": report.failed_cases,
        "timeout_cases": report.timeout_cases,
        "skip_generation": skip_generation,
        "tool_dry_run": tool_dry_run,
        "case_results": [
            {
                "case_id": c.case_id,
                "question": c.question,
                "intent_correct": c.intent_correct,
                "doc_hit": c.doc_hit,
                "tool_call_correct": c.tool_call_correct,
                "has_citation": c.has_citation,
                "forbidden_doc_leaked": c.forbidden_doc_leaked,
                "latency_ms": c.latency_ms,
                "timed_out": c.timed_out,
                "detail": c.detail,
            }
            for c in report.case_results
        ],
    }
    # 落库，供后台对比（P1-5）
    try:
        from db.session import async_session_factory
        from db.models import EvalRun
        from datetime import datetime, timezone
        async with async_session_factory() as db:
            db.add(EvalRun(
                finished_at=datetime.now(timezone.utc),
                total_cases=payload["total_cases"],
                scored_cases=payload["scored_cases"],
                timeout_count=payload["timeout_count"],
                intent_accuracy=payload["intent_accuracy"],
                doc_hit_rate=payload["doc_hit_rate"],
                tool_call_accuracy=payload["tool_call_accuracy"],
                citation_rate=payload["citation_rate"],
                permission_pass_rate=payload["permission_pass_rate"],
                avg_latency_ms=payload["avg_latency_ms"],
                skip_generation=skip_generation,
                tool_dry_run=tool_dry_run,
                case_results=payload["case_results"],
                failed_cases=payload["failed_cases"],
                operator_id=current_user.id,
            ))
            await db.commit()
    except Exception:
        pass  # 落库失败不影响评测返回

    return BaseResp.ok(payload)
