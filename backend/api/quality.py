"""评测结果查询 + 用户反馈 + 知识缺口。

落库入口统一在 POST /api/eval/run（eval.py），本模块只读 eval_runs。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_active_user, require_admin, require_super_admin
from db.models import EvalRun, QARecord, User, UserRole
from db.session import get_db
from schemas.common import BaseResp, PagedData

router = APIRouter()


class FeedbackBody(BaseModel):
    feedback: str = Field(..., pattern="^(up|down)$")
    reason: str | None = None  # answer_wrong / citation_wrong / not_found / other


class GapResolveBody(BaseModel):
    resolved: bool = True


# ── 评测结果查询（落库由 /api/eval/run 完成）──────────────────

@router.get("/runs", response_model=BaseResp[list[dict]])
async def list_eval_runs(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(select(EvalRun).order_by(EvalRun.started_at.desc()).limit(20))
    ).scalars().all()
    return BaseResp.ok([
        {
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "total_cases": r.total_cases,
            "scored_cases": r.scored_cases,
            "timeout_count": r.timeout_count,
            "intent_accuracy": r.intent_accuracy,
            "doc_hit_rate": r.doc_hit_rate,
            "mrr": r.mrr,
            "tool_call_accuracy": r.tool_call_accuracy,
            "citation_rate": r.citation_rate,
            "permission_pass_rate": r.permission_pass_rate,
            "avg_latency_ms": r.avg_latency_ms,
            "failed_cases": r.failed_cases,
            "note": r.note,
            "label": r.label,
            "mode": r.mode or "fast",
            "status": r.status or "finished",
            "progress": r.progress,
            "judge_model": r.judge_model,
            "faithfulness_avg": r.faithfulness_avg,
            "points_coverage": r.points_coverage,
            "hallucination_count": r.hallucination_count,
            "refusal_correct_rate": r.refusal_correct_rate,
            "prompt_set_version": r.prompt_set_version,
        }
        for r in rows
    ])


@router.get("/runs/{run_id}", response_model=BaseResp[dict])
async def get_eval_run(
    run_id: int,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    r = await db.scalar(select(EvalRun).where(EvalRun.id == run_id))
    if not r:
        raise HTTPException(404, detail={"code": 40400, "message": "评测记录不存在"})
    case_results = r.case_results or []
    return BaseResp.ok({
        "id": r.id,
        "mode": r.mode or "fast",
        "label": r.label,
        "status": r.status or "finished",
        "progress": r.progress,
        "total_cases": r.total_cases,
        "scored_cases": r.scored_cases,
        "case_results": case_results,
        "failed_cases": r.failed_cases,
        "note": r.note,
        "judge_model": r.judge_model,
        "faithfulness_avg": r.faithfulness_avg,
        "points_coverage": r.points_coverage,
        "hallucination_count": r.hallucination_count,
        "refusal_correct_rate": r.refusal_correct_rate,
        "prompt_set_version": r.prompt_set_version,
        "metrics": {
            "intent_accuracy": r.intent_accuracy,
            "doc_hit_rate": r.doc_hit_rate,
            "mrr": r.mrr,
            "tool_call_accuracy": r.tool_call_accuracy,
            "citation_rate": r.citation_rate,
            "permission_pass_rate": r.permission_pass_rate,
            "faithfulness_avg": r.faithfulness_avg,
            "points_coverage": r.points_coverage,
            "hallucination_count": r.hallucination_count,
            "refusal_correct_rate": r.refusal_correct_rate,
        },
        "judge_cases": [
            {
                "case_id": c.get("case_id"),
                "question": c.get("question"),
                "group": c.get("group"),
                "judge": c.get("judge"),
                "answer_preview": c.get("answer_preview"),
            }
            for c in case_results
            if c.get("judge")
        ],
    })


@router.get("/runs/{run_id}/diff", response_model=BaseResp[dict])
async def diff_eval_runs(
    run_id: int,
    other_id: int = Query(..., description="对比 run id"),
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """两次运行 case 级 diff：通过↔失败。"""
    a = await db.scalar(select(EvalRun).where(EvalRun.id == run_id))
    b = await db.scalar(select(EvalRun).where(EvalRun.id == other_id))
    if not a or not b:
        raise HTTPException(404, detail={"code": 40400, "message": "评测记录不存在"})

    def _passed(c: dict) -> bool:
        j = c.get("judge") or {}
        if j.get("error"):
            return False
        if j.get("hallucinated_claims"):
            return False
        return bool(
            c.get("intent_correct")
            and c.get("doc_hit")
            and c.get("tool_call_correct")
            and c.get("has_citation")
            and not c.get("forbidden_doc_leaked")
        )

    def _index(run: EvalRun) -> dict[str, dict]:
        return {c.get("case_id"): c for c in (run.case_results or []) if c.get("case_id")}

    ia, ib = _index(a), _index(b)
    all_ids = sorted(set(ia) | set(ib))
    became_pass, became_fail, still_fail = [], [], []
    for cid in all_ids:
        ca, cb = ia.get(cid), ib.get(cid)
        pa = _passed(ca) if ca else False
        pb = _passed(cb) if cb else False
        question = (cb or ca or {}).get("question") or cid
        group = (cb or ca or {}).get("group") or ""
        item = {"case_id": cid, "question": question, "group": group,
                "a_passed": pa, "b_passed": pb}
        if ca and cb:
            if not pa and pb:
                became_pass.append(item)
            elif pa and not pb:
                became_fail.append(item)
            elif not pa and not pb:
                still_fail.append(item)
    by_group = {}
    for item in became_fail + became_pass + still_fail:
        g = item["group"] or "default"
        by_group.setdefault(g, {"became_pass": 0, "became_fail": 0, "still_fail": 0})
        if item in became_pass:
            by_group[g]["became_pass"] += 1
        elif item in became_fail:
            by_group[g]["became_fail"] += 1
        else:
            by_group[g]["still_fail"] += 1
    return BaseResp.ok({
        "run_a": {"id": a.id, "label": a.label, "mode": a.mode,
                  "prompt_set_version": a.prompt_set_version},
        "run_b": {"id": b.id, "label": b.label, "mode": b.mode,
                  "prompt_set_version": b.prompt_set_version},
        "prompt_changed": (a.prompt_set_version or "") != (b.prompt_set_version or ""),
        "became_pass": became_pass,
        "became_fail": became_fail,
        "still_fail": still_fail,
        "by_group": by_group,
    })


# ── 用户反馈 ─────────────────────────────────────────────────

@router.post("/feedback/{qa_id}", response_model=BaseResp[None])
async def submit_feedback(
    qa_id: int,
    body: FeedbackBody,
    current_user: User = Depends(get_active_user),
    db: AsyncSession = Depends(get_db),
):
    if body.feedback not in ("up", "down"):
        raise HTTPException(400, detail={"code": 40010, "message": "feedback 必须是 up/down"})
    rec = await db.scalar(
        select(QARecord).where(QARecord.id == qa_id, QARecord.user_id == current_user.id)
    )
    if not rec:
        raise HTTPException(404, detail={"code": 40400, "message": "记录不存在"})
    rec.feedback = body.feedback
    rec.feedback_reason = body.reason
    if body.feedback == "down":
        rec.is_gap = True
    await db.commit()
    return BaseResp.ok(message="感谢反馈")


# ── 知识缺口 ─────────────────────────────────────────────────

@router.get("/gaps", response_model=BaseResp[PagedData[dict]])
async def list_gaps(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    resolved: bool = Query(False),
    dept_id: int | None = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(QARecord).where(QARecord.is_gap == True)  # noqa: E712
    q = q.where(QARecord.gap_resolved == resolved)
    if current_user.role == UserRole.dept_admin:
        q = q.where(QARecord.dept_id == current_user.dept_id)
    elif dept_id:
        q = q.where(QARecord.dept_id == dept_id)

    total = await db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = (
        await db.execute(
            q.order_by(QARecord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    # 全库按 query 前 20 字聚合频次（SQL，跨页有效）
    prefix_expr = func.substr(QARecord.query, 1, 20)
    freq_q = (
        select(prefix_expr.label("pfx"), func.count().label("cnt"))
        .where(QARecord.is_gap == True)  # noqa: E712
        .where(QARecord.gap_resolved == resolved)
        .group_by(prefix_expr)
    )
    if current_user.role == UserRole.dept_admin:
        freq_q = freq_q.where(QARecord.dept_id == current_user.dept_id)
    elif dept_id:
        freq_q = freq_q.where(QARecord.dept_id == dept_id)
    freq_rows = (await db.execute(freq_q)).all()
    freq = {r.pfx: int(r.cnt) for r in freq_rows}

    items = [
        {
            "id": r.id,
            "query": r.query,
            "intent": r.intent,
            "top1_score": r.top1_score,
            "doc_hit": r.doc_hit,
            "feedback": r.feedback,
            "feedback_reason": r.feedback_reason,
            "answer_preview": r.answer_preview,
            "dept_id": r.dept_id,
            "user_id": r.user_id,
            "freq": freq.get((r.query or "")[:20], 1),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return BaseResp.ok(PagedData(items=items, total=total, page=page, page_size=page_size))


async def _load_gap_for_admin(db: AsyncSession, qa_id: int, current_user: User) -> QARecord:
    rec = await db.scalar(select(QARecord).where(QARecord.id == qa_id))
    if not rec:
        raise HTTPException(404, detail={"code": 40400, "message": "记录不存在"})
    if current_user.role == UserRole.dept_admin:
        if rec.dept_id != current_user.dept_id:
            raise HTTPException(403, detail={"code": 40301, "message": "无权操作其他部门的记录"})
    return rec


@router.post("/gaps/{qa_id}/resolve", response_model=BaseResp[None])
async def resolve_gap(
    qa_id: int,
    body: GapResolveBody,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rec = await _load_gap_for_admin(db, qa_id, current_user)
    rec.gap_resolved = body.resolved
    await db.commit()
    return BaseResp.ok(message="已更新")


@router.post("/gaps/{qa_id}/to_eval", response_model=BaseResp[dict])
async def gap_to_eval(
    qa_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    场景 C：知识缺口 → eval_cases 表（不再写源码树 cases.json）。
    """
    rec = await _load_gap_for_admin(db, qa_id, current_user)
    question = (rec.query or "").strip()
    if not question:
        raise HTTPException(400, detail={"code": 40010, "message": "问题为空，无法入库"})

    from db.models import EvalCase
    existing = await db.scalar(
        select(EvalCase).where(EvalCase.question == question, EvalCase.active == True)  # noqa: E712
    )
    if existing:
        return BaseResp.ok({
            "case_id": existing.case_id,
            "message": "该问题已在评测集中",
            "duplicated": True,
        })

    # 取下一个 case 编号
    from sqlalchemy import func
    max_num = await db.scalar(
        select(func.max(EvalCase.case_id))
    )
    n = 1
    if max_num and str(max_num).startswith("case_"):
        try:
            n = int(str(max_num).split("_", 1)[1]) + 1
        except ValueError:
            n = 1
    else:
        cnt = await db.scalar(select(func.count()).select_from(EvalCase)) or 0
        n = cnt + 1
    case_id = f"case_{n:03d}"

    payload = {
        "id": case_id,
        "question": question,
        "expected_intent": rec.intent or "rag",
        "should_cite": True,
        "group": "gap",
        "description": f"知识缺口导入 qa_id={qa_id}",
    }
    db.add(EvalCase(
        case_id=case_id,
        question=question,
        group="gap",
        payload=payload,
        source="gap",
        active=True,
        created_by=current_user.id,
    ))
    await db.commit()
    return BaseResp.ok({
        "case_id": case_id,
        "question": question,
        "message": "已写入 eval_cases，重跑 eval 生效",
        "duplicated": False,
    })


@router.post("/cases/seed", response_model=BaseResp[dict])
async def seed_cases_from_json(
    current_user: User = Depends(require_super_admin),
):
    """把 eval/cases.json 导入 eval_cases 表（首次或 json 更新后调用）。"""
    from eval.runner import seed_eval_cases_from_json

    n = await seed_eval_cases_from_json(created_by=current_user.id)
    return BaseResp.ok({"imported": n})


# ── Q4 评测 Case 管理 ─────────────────────────────────────────

class EvalCaseBody(BaseModel):
    case_id: str | None = None
    question: str
    group: str | None = None
    payload: dict
    active: bool = True


class EvalCasePatch(BaseModel):
    question: str | None = None
    group: str | None = None
    payload: dict | None = None
    active: bool | None = None


def _case_out(row) -> dict:
    return {
        "id": row.id,
        "case_id": row.case_id,
        "question": row.question,
        "group": row.group,
        "payload": row.payload,
        "source": row.source,
        "active": row.active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/eval-cases", response_model=BaseResp[PagedData[dict]])
async def list_eval_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    group: str | None = Query(None),
    active: bool | None = Query(None),
    keyword: str | None = Query(None, max_length=100),
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from db.models import EvalCase

    conditions = []
    if group:
        conditions.append(EvalCase.group == group)
    if active is not None:
        conditions.append(EvalCase.active == active)
    if keyword:
        conditions.append(EvalCase.question.ilike(f"%{keyword}%"))

    count_stmt = select(func.count(EvalCase.id))
    data_stmt = select(EvalCase).order_by(EvalCase.case_id.asc())
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
        data_stmt = data_stmt.where(cond)
    total = await db.scalar(count_stmt) or 0
    rows = (
        await db.execute(data_stmt.offset((page - 1) * page_size).limit(page_size))
    ).scalars().all()

    groups = (
        await db.execute(select(EvalCase.group).distinct())
    ).scalars().all()
    return BaseResp.ok(PagedData(
        items=[_case_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    ))


@router.get("/eval-cases/groups", response_model=BaseResp[list[str]])
async def list_eval_case_groups(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from db.models import EvalCase
    rows = (
        await db.execute(select(EvalCase.group).where(EvalCase.group.isnot(None)).distinct())
    ).scalars().all()
    return BaseResp.ok(sorted([g for g in rows if g]))


@router.get("/eval-cases/{case_id}", response_model=BaseResp[dict])
async def get_eval_case(
    case_id: str,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from db.models import EvalCase
    row = await db.scalar(select(EvalCase).where(EvalCase.case_id == case_id))
    if not row:
        raise HTTPException(404, detail={"code": 40400, "message": "case 不存在"})
    # 最近一次结果
    last = await db.scalar(select(EvalRun).order_by(EvalRun.id.desc()).limit(1))
    last_result = None
    if last and last.case_results:
        for c in last.case_results:
            if c.get("case_id") == case_id:
                last_result = c
                break
    out = _case_out(row)
    out["last_run"] = {
        "run_id": last.id if last else None,
        "mode": last.mode if last else None,
        "label": last.label if last else None,
        "result": last_result,
    } if last else None
    return BaseResp.ok(out)


@router.post("/eval-cases", response_model=BaseResp[dict])
async def create_eval_case(
    body: EvalCaseBody,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from db.models import EvalCase

    cid = body.case_id or body.payload.get("id")
    if not cid:
        n = await db.scalar(select(func.count(EvalCase.id))) or 0
        cid = f"case_{n + 1:03d}"
    existing = await db.scalar(select(EvalCase).where(EvalCase.case_id == cid))
    if existing:
        raise HTTPException(409, detail={"code": 40900, "message": f"case_id 已存在: {cid}"})
    payload = dict(body.payload or {})
    payload.setdefault("id", cid)
    payload.setdefault("question", body.question)
    if body.group:
        payload["group"] = body.group
    row = EvalCase(
        case_id=cid,
        question=body.question,
        group=body.group or payload.get("group"),
        payload=payload,
        source="manual",
        active=body.active,
        created_by=current_user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return BaseResp.ok(_case_out(row), message="已创建")


@router.patch("/eval-cases/{case_id}", response_model=BaseResp[dict])
async def update_eval_case(
    case_id: str,
    body: EvalCasePatch,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    from db.models import EvalCase
    row = await db.scalar(select(EvalCase).where(EvalCase.case_id == case_id))
    if not row:
        raise HTTPException(404, detail={"code": 40400, "message": "case 不存在"})
    if body.question is not None:
        row.question = body.question
        row.payload = {**(row.payload or {}), "question": body.question}
    if body.group is not None:
        row.group = body.group
        row.payload = {**(row.payload or {}), "group": body.group}
    if body.payload is not None:
        row.payload = body.payload
        row.question = body.payload.get("question") or row.question
        row.group = body.payload.get("group") or row.group
    if body.active is not None:
        row.active = body.active
        row.payload = {**(row.payload or {}), "active": body.active}
    await db.commit()
    await db.refresh(row)
    return BaseResp.ok(_case_out(row), message="已更新")
