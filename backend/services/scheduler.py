"""P2：APScheduler + PostgreSQLJobStore，多 worker 只跑一次。"""
from __future__ import annotations

import asyncio
from typing import Optional

from core.config import settings
from core.logger import logger

_scheduler = None
_started = False


def _sync_db_url() -> str:
    url = settings.database_url
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://").replace(
        "+asyncpg", "+psycopg2"
    ) if "asyncpg" in url else url


def get_scheduler():
    return _scheduler


async def job_cleanup() -> None:
    """模块级 job（SQLAlchemyJobStore 可序列化引用）。"""
    from services.cleanup import run_cleanup_once
    logger.info("[scheduler] job start | cleanup")
    try:
        stats = await run_cleanup_once()
        logger.info("[scheduler] job done | cleanup | {s}", s=stats)
    except Exception as exc:
        logger.error(f"[scheduler] job failed | cleanup | {type(exc).__name__}: {exc}")
        await write_job_audit("cleanup", f"{type(exc).__name__}: {exc}")


async def job_daily_report() -> None:
    from services.daily_report import generate_all_department_reports
    logger.info("[scheduler] job start | daily_report")
    try:
        n = await generate_all_department_reports()
        logger.info("[scheduler] job done | daily_report | n={n}", n=n)
    except Exception as exc:
        logger.error(f"[scheduler] job failed | daily_report | {type(exc).__name__}: {exc}")
        await write_job_audit("daily_report", f"{type(exc).__name__}: {exc}")


async def write_job_audit(job: str, detail: str) -> None:
    try:
        from db.models import AuditLog
        from db.session import async_session_factory
        async with async_session_factory() as db:
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
    except Exception as exc:
        logger.warning(f"[scheduler] audit write failed: {exc}")


async def start_scheduler() -> None:
    """启动全局调度器。Job 函数必须在模块顶层，才能被 JobStore 序列化。"""
    global _scheduler, _started
    if not settings.scheduler_enabled:
        logger.info("[scheduler] disabled by config")
        return
    if _started and _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("[scheduler] apscheduler 未安装，跳过定时任务")
        return

    try:
        jobstores = {
            "default": SQLAlchemyJobStore(url=_sync_db_url()),
        }
        _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
        _scheduler.add_job(
            "services.scheduler:job_cleanup",
            CronTrigger(minute="17"),
            id="cleanup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            "services.scheduler:job_daily_report",
            CronTrigger(hour=settings.daily_report_hour, minute="5"),
            id="daily_report",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.start()
        _started = True
        logger.info(
            "[scheduler] started | jobs=cleanup,daily_report | report_hour={h}",
            h=settings.daily_report_hour,
        )
    except Exception as exc:
        logger.error(f"[scheduler] 启动失败: {type(exc).__name__}: {exc}")


def stop_scheduler() -> None:
    global _scheduler, _started
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
    _scheduler = None
    _started = False
