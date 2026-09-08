"""Eval API — 运行评测并返回结果。"""
from fastapi import APIRouter, Depends
from core.deps import require_super_admin
from db.models import User
from eval.runner import run_eval
from schemas.common import BaseResp

router = APIRouter()


@router.post("/run", response_model=BaseResp[dict])
async def run_evaluation(
    current_user: User = Depends(require_super_admin),
):
    report = await run_eval(
        user_id=current_user.id,
        user_role=current_user.role.value,
        user_dept_id=current_user.dept_id,
    )
    return BaseResp.ok({
        "total_cases": report.total_cases,
        "intent_accuracy": report.intent_accuracy,
        "doc_hit_rate": report.doc_hit_rate,
        "tool_call_accuracy": report.tool_call_accuracy,
        "citation_rate": report.citation_rate,
        "avg_latency_ms": report.avg_latency_ms,
        "failed_cases": report.failed_cases,
    })