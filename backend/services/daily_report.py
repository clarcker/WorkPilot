"""P9：部门运营日报 + notifications。数据 SQL 汇总，LLM 只写摘要。"""
from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import func, select, text

from core.logger import logger
from db.models import (
    AgentTrace,
    AuditLog,
    Department,
    EvalRun,
    ItTicket,
    Notification,
    QARecord,
    ReimbursementRequest,
)
from db.session import async_session_factory


async def write_scheduler_audit(job: str, detail: str) -> None:
    from db.session import async_session_factory as sf
    async with sf() as db:
        db.add(AuditLog(
            operator_id=None,
            operator_name="scheduler",
            action="scheduler.job_failed",
            resource_type="job",
            resource_id=job,
            detail=detail[:2000],
            result="failed",
        ))
        await db.commit()


async def _sql_summary(db, dept_id: int | None, since) -> dict[str, Any]:
    conds = [QARecord.created_at >= since]
    if dept_id is not None:
        conds.append(QARecord.dept_id == dept_id)
    qa_total = await db.scalar(select(func.count(QARecord.id)).where(*conds)) or 0
    qa_down = await db.scalar(
        select(func.count(QARecord.id)).where(*conds, QARecord.feedback == "down")
    ) or 0
    gap_q = select(QARecord.query, func.count(QARecord.id).label("c")).where(
        QARecord.created_at >= since,
        QARecord.is_gap == True,  # noqa: E712
        QARecord.gap_resolved == False,  # noqa: E712
    )
    if dept_id is not None:
        gap_q = gap_q.where(QARecord.dept_id == dept_id)
    gaps = (await db.execute(gap_q.group_by(QARecord.query).order_by(text("c DESC")).limit(5))).all()

    reimb_q = select(func.count(ReimbursementRequest.id)).where(
        ReimbursementRequest.status == "pending"
    )
    if dept_id is not None:
        reimb_q = reimb_q.where(ReimbursementRequest.dept_id == dept_id)
    pending_reimb = await db.scalar(reimb_q) or 0
    cutoff = since - datetime.timedelta(hours=24)
    old_reimb = await db.scalar(
        reimb_q.where(ReimbursementRequest.created_at < cutoff)
    ) or 0

    ticket_q = select(func.count(ItTicket.id)).where(ItTicket.status == "open")
    pending_tickets = await db.scalar(ticket_q) or 0
    old_tickets = await db.scalar(
        select(func.count(ItTicket.id)).where(
            ItTicket.status == "open",
            ItTicket.created_at < cutoff,
        )
    ) or 0

    last_eval = await db.scalar(select(EvalRun).order_by(EvalRun.id.desc()).limit(1))
    eval_alert = None
    if last_eval and last_eval.doc_hit_rate is not None and last_eval.doc_hit_rate < 0.75:
        eval_alert = f"最近 eval run#{last_eval.id} doc_hit={last_eval.doc_hit_rate:.3f} 偏低"

    return {
        "qa_total": qa_total,
        "qa_down": qa_down,
        "gaps": [{"query": g[0], "count": g[1]} for g in gaps],
        "pending_reimb": pending_reimb,
        "pending_reimb_over_48h": old_reimb,
        "pending_tickets": pending_tickets,
        "pending_tickets_over_48h": old_tickets,
        "eval_alert": eval_alert,
        "eval_run_id": last_eval.id if last_eval else None,
        "eval_doc_hit": last_eval.doc_hit_rate if last_eval else None,
        "eval_mrr": last_eval.mrr if last_eval else None,
    }


def _structured_bullets(dept_name: str, data: dict) -> str:
    lines = [
        f"【{dept_name} 运营日报】",
        f"- 昨日问答 {data['qa_total']} 条，👎 {data['qa_down']} 条",
        "- 知识缺口 Top：",
    ]
    if data["gaps"]:
        for g in data["gaps"]:
            lines.append(f"  · {g['query']}（{g['count']} 次）— 建议补充对应制度文档")
    else:
        lines.append("  · 无")
    lines.append(
        f"- 待审批报销 {data['pending_reimb']}（超48h {data['pending_reimb_over_48h']}）"
    )
    lines.append(
        f"- 待处理工单 {data['pending_tickets']}（超48h {data['pending_tickets_over_48h']}）"
    )
    if data.get("eval_alert"):
        lines.append(f"- 告警：{data['eval_alert']}")
    elif data.get("eval_run_id"):
        lines.append(
            f"- 最近评测 run#{data['eval_run_id']} doc_hit={data['eval_doc_hit']} mrr={data['eval_mrr']}"
        )
    return "\n".join(lines)


async def _llm_summarize(bullets: str) -> str:
    """LLM 只润色；失败则返回结构化原文，禁止编造数字。"""
    try:
        from services.llm_client import chat_complete
        prompt = (
            "把下列企业运营数据改写成 3-5 句中文摘要。"
            "只能使用数据中出现的数字，禁止添加或估算。\n\n" + bullets
        )
        out = await chat_complete(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300,
            user_role="super_admin",
        )
        return out.strip() or bullets
    except Exception as exc:
        logger.warning(f"[daily_report] LLM 摘要失败，使用结构化原文: {exc}")
        return bullets


async def generate_department_report(dept: Department) -> int:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    async with async_session_factory() as db:
        data = await _sql_summary(db, dept.id, since)
        admin_id = await db.scalar(
            text(
                "SELECT id FROM users WHERE dept_id=:d AND role IN ('dept_admin','super_admin') "
                "ORDER BY CASE role WHEN 'super_admin' THEN 0 ELSE 1 END LIMIT 1"
            ),
            {"d": dept.id},
        )
        if admin_id is None:
            admin_id = await db.scalar(
                text("SELECT id FROM users WHERE role='super_admin' LIMIT 1")
            )
        if admin_id is None:
            return 0

    bullets = _structured_bullets(dept.dept_name, data)
    summary = await _llm_summarize(bullets)
    body = summary + "\n\n---\n数据明细\n" + bullets
    title = f"{dept.dept_name} 运营日报 {datetime.date.today().isoformat()}"

    async with async_session_factory() as db:
        n = Notification(
            user_id=int(admin_id),
            title=title,
            body=body[:4000],
            level="warning" if data.get("eval_alert") or data["pending_reimb_over_48h"] or data["pending_tickets_over_48h"] else "info",
            source="daily_report",
            payload=data,
            is_read=False,
        )
        db.add(n)
        db.add(AgentTrace(
            conversation_id=None,
            user_id=int(admin_id),
            query=f"[scheduled] daily_report dept={dept.dept_code}",
            intent="system",
            steps=[{
                "node": "daily_report",
                "output_summary": f"qa={data['qa_total']} gaps={len(data['gaps'])} reimb={data['pending_reimb']}",
                "latency_ms": 0,
            }],
            final_answer=summary[:2000],
            sources=None,
            llm_model="llm_summary",
        ))
        await db.commit()
        return int(n.id)


async def generate_all_department_reports() -> int:
    async with async_session_factory() as db:
        depts = (await db.execute(select(Department))).scalars().all()
    total = 0
    for d in depts:
        try:
            total += await generate_department_report(d)
        except Exception as exc:
            logger.error(f"[daily_report] dept={d.dept_code} failed: {exc}")
            await write_scheduler_audit(f"daily_report:{d.dept_code}", f"{exc}")
    logger.info(f"[daily_report] generated {total} notifications")
    return total
