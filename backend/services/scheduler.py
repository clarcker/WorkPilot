"""P2：调度只在选主 worker 上启动。

APScheduler 3.x 的 JobStore 只持久化 **job 定义**，每个进程的 scheduler
会各自触发。多 worker 防重必须 **进程级选主**：
启动时在专用连接上 `pg_try_advisory_lock`，锁随连接存活；仅 leader 启动
scheduler。非 leader 不跑 cleanup_loop。
"""
from __future__ import annotations

import asyncio
from typing import Optional

from core.config import settings
from core.logger import logger

_scheduler = None
_started = False
_is_leader = False
_lock_conn = None  # 专用 asyncpg 连接，持有 advisory lock
_lock_hold_task: Optional[asyncio.Task] = None
_follower_task: Optional[asyncio.Task] = None  # 防 asyncio 弱引用 GC

# 与 cleanup 共用同一常量，避免两套锁语义
SCHEDULER_ADVISORY_LOCK_ID = 918273645


def _sync_db_url() -> str:
    url = settings.database_url
    return url.replace("+asyncpg", "+psycopg2") if "asyncpg" in url else url


def _asyncpg_dsn() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


def get_scheduler():
    return _scheduler


def is_scheduler_leader() -> bool:
    return _is_leader


async def job_cleanup() -> None:
    """模块级 job（SQLAlchemyJobStore 可序列化引用）。仅 leader 会调度到。"""
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


async def _try_become_leader() -> bool:
    """专用连接持有 advisory lock；成功返回 True。连接断开则锁自动释放。"""
    global _lock_conn
    try:
        import asyncpg
        dsn = _asyncpg_dsn()
        conn = await asyncpg.connect(dsn, timeout=10)
        got = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)", SCHEDULER_ADVISORY_LOCK_ID
        )
        if not got:
            await conn.close()
            return False
        _lock_conn = conn
        return True
    except Exception as exc:
        logger.warning(f"[scheduler] 选主失败（不启动调度）: {type(exc).__name__}: {exc}")
        return False


async def _hold_leader_lock() -> None:
    """
    保持连接；锁丢失 → 立刻 shutdown 本进程 scheduler，避免与新 leader 双跑。
    非 leader 另有 _follower_retry_loop 重试抢锁。
    """
    global _is_leader, _lock_conn, _started, _scheduler
    while _lock_conn is not None:
        try:
            await _lock_conn.fetchval("SELECT 1")
        except Exception as exc:
            logger.warning(f"[scheduler] leader 锁连接丢失，shutdown 本进程调度: {exc}")
            _is_leader = False
            _lock_conn = None
            _started = False
            if _scheduler is not None:
                try:
                    _scheduler.shutdown(wait=False)
                except Exception:
                    pass
                _scheduler = None
            _spawn_follower_task()  # 锁丢后本进程重新参与选主
            return
        await asyncio.sleep(30)


def _spawn_follower_task() -> None:
    global _follower_task
    if _follower_task is not None and not _follower_task.done():
        return
    _follower_task = asyncio.create_task(_follower_retry_loop())


def _build_and_start_scheduler() -> None:
    """建 job 并启动；start_scheduler 与 follower 接管共用。"""
    global _scheduler, _started, _is_leader, _lock_hold_task
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from apscheduler.triggers.cron import CronTrigger

    jobstores = {"default": SQLAlchemyJobStore(url=_sync_db_url())}
    _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=settings.scheduler_timezone)
    _scheduler.add_job(
        "services.scheduler:job_cleanup",
        CronTrigger(minute="17"),
        id="cleanup", replace_existing=True, max_instances=1, coalesce=True,
    )
    _scheduler.add_job(
        "services.scheduler:job_daily_report",
        CronTrigger(hour=settings.daily_report_hour, minute="5"),
        id="daily_report", replace_existing=True, max_instances=1, coalesce=True,
    )
    _scheduler.start()
    _started = True
    _is_leader = True
    _lock_hold_task = asyncio.create_task(_hold_leader_lock())
    logger.info(
        "[scheduler] leader 启动调度 | jobs=cleanup,daily_report | "
        "report_hour={h} tz={tz} | lock_id={lid}",
        h=settings.daily_report_hour,
        tz=settings.scheduler_timezone,
        lid=SCHEDULER_ADVISORY_LOCK_ID,
    )


async def _follower_retry_loop() -> None:
    """非 leader 每 60s 重试抢锁；成功则启动调度（leader 宕机接管）。"""
    global _is_leader, _started
    while not _is_leader and settings.scheduler_enabled:
        await asyncio.sleep(60)
        if _is_leader or _started:
            return
        if await _try_become_leader():
            logger.info("[scheduler] 原 leader 失联，本 worker 接管")
            try:
                _build_and_start_scheduler()
            except Exception as exc:
                logger.error(f"[scheduler] 接管启动失败: {exc}")
                _is_leader = False
            return


async def start_scheduler() -> None:
    """
    多 worker：仅 advisory lock 选主成功的进程启动 APScheduler。
    非 leader 每 60s 重试抢锁；leader 锁丢失则 shutdown 自身并重回 follower。
    """
    global _started, _is_leader
    if not settings.scheduler_enabled:
        logger.info("[scheduler] disabled by config")
        return
    if _started and _scheduler is not None:
        return

    if not await _try_become_leader():
        _is_leader = False
        logger.info("[scheduler] 本 worker 非 leader，60s 后重试抢锁；不执行 cleanup")
        _spawn_follower_task()
        return

    try:
        _build_and_start_scheduler()
    except Exception as exc:
        logger.error(f"[scheduler] 启动失败: {type(exc).__name__}: {exc}")
        _is_leader = False


def stop_scheduler() -> None:
    global _scheduler, _started, _is_leader, _lock_conn, _lock_hold_task, _follower_task
    for t in (_lock_hold_task, _follower_task):
        if t is not None:
            t.cancel()
    _lock_hold_task = None
    _follower_task = None
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
    if _lock_conn is not None:
        try:
            # 释放锁并关闭连接
            asyncio.get_event_loop().create_task(_release_lock_async())
        except Exception:
            pass
    _scheduler = None
    _started = False
    _is_leader = False


async def _release_lock_async() -> None:
    global _lock_conn
    conn = _lock_conn
    _lock_conn = None
    if conn is None:
        return
    try:
        await conn.execute("SELECT pg_advisory_unlock($1)", SCHEDULER_ADVISORY_LOCK_ID)
    except Exception:
        pass
    try:
        await conn.close()
    except Exception:
        pass
