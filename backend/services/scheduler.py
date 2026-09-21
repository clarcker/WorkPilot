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


async def start_scheduler() -> None:
    """启动全局调度器。多 worker 各起进程但 JobStore 在 PG，trigger 只触发一次执行锁。"""
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
        from services.cleanup import run_cleanup_once
        from services.daily_report import generate_all_department_reports

        _scheduler.add_job(
            _run_job_logged(run_cleanup_once, "cleanup"),
            CronTrigger(minute="17"),  # 避开整点，降低多 worker 撞车
            id="cleanup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            _run_job_logged(generate_all_department_reports, "daily_report"),
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


def _run_job_logged(fn, name: str):
    async def _wrapper():
        logger.info(f"[scheduler] job start | {name}")
        try:
            await fn()
            logger.info(f"[scheduler] job done | {name}")
        except Exception as exc:
            logger.error(f"[scheduler] job failed | {name} | {type(exc).__name__}: {exc}")
            try:
                # 失败审计（同步写，best-effort）
                import asyncio as _aio
                from services.daily_report import write_scheduler_audit
                await write_scheduler_audit(name, f"{type(exc).__name__}: {exc}")
            except Exception:
                pass

    return _wrapper


def stop_scheduler() -> None:
    global _scheduler, _started
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
    _scheduler = None
    _started = False
