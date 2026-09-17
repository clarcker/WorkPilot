"""
后台清理任务：归档会话过期物理删除 + 过期吊销 token 清理。

设计文档要求 APScheduler + PostgreSQLJobStore；Phase 1 仅单机开发/部署，
用 asyncio 周期任务即可，避免多一层依赖。多 Worker 生产部署时再换
APScheduler + JobStore（见 系统架构.md A.2）。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from core.logger import logger
from db.models import Conversation, ConversationStatus, Message, RevokedToken, SystemConfig
from db.session import async_session_factory

# 默认清理间隔 24h；开发环境可缩短便于验证
_CLEANUP_INTERVAL_SECONDS = 24 * 3600
_DEFAULT_RETENTION_DAYS = 180


async def _load_retention_days() -> int:
    async with async_session_factory() as db:
        raw = await db.scalar(
            select(SystemConfig.value).where(SystemConfig.key == "archive_retention_days")
        )
    if raw is None:
        return _DEFAULT_RETENTION_DAYS
    if isinstance(raw, dict) and "value" in raw:
        raw = raw["value"]
    try:
        days = int(raw)
        return days if days > 0 else _DEFAULT_RETENTION_DAYS
    except (TypeError, ValueError):
        return _DEFAULT_RETENTION_DAYS


async def cleanup_expired_archived_conversations() -> dict:
    """物理删除归档超过保留期的会话及其消息。返回统计。"""
    retention_days = await _load_retention_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    async with async_session_factory() as db:
        expired = await db.execute(
            select(Conversation.id).where(
                Conversation.status == ConversationStatus.archived,
                Conversation.updated_at < cutoff,
            )
        )
        conv_ids = [row[0] for row in expired.all()]
        if not conv_ids:
            return {"conversations": 0, "messages": 0, "retention_days": retention_days}

        msg_result = await db.execute(
            delete(Message).where(Message.conversation_id.in_(conv_ids))
        )
        await db.execute(
            delete(Conversation).where(Conversation.id.in_(conv_ids))
        )
        await db.commit()
        stats = {
            "conversations": len(conv_ids),
            "messages": msg_result.rowcount or 0,
            "retention_days": retention_days,
        }
        logger.info(
            "[cleanup] 归档会话过期删除 | convs={c} msgs={m} retention={d}d",
            c=stats["conversations"], m=stats["messages"], d=retention_days,
        )
        return stats


async def cleanup_expired_revoked_tokens() -> int:
    """删除已过期的 JWT 黑名单记录（token 本身已无效，黑名单无需再留）。"""
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        result = await db.execute(
            delete(RevokedToken).where(RevokedToken.expires_at < now)
        )
        await db.commit()
        n = result.rowcount or 0
    if n:
        logger.info("[cleanup] 过期吊销 token 清理 | count={n}", n=n)
    return n


async def run_cleanup_once() -> dict:
    """执行一轮完整清理（供启动预热或手动触发）。"""
    conv_stats = await cleanup_expired_archived_conversations()
    token_n = await cleanup_expired_revoked_tokens()
    return {**conv_stats, "revoked_tokens": token_n}


async def cleanup_loop(stop_event: asyncio.Event, interval: float = _CLEANUP_INTERVAL_SECONDS) -> None:
    """周期清理循环，直到 stop_event 被设置。"""
    logger.info("[cleanup] 后台清理任务启动 | interval={s}s", s=interval)
    while not stop_event.is_set():
        try:
            await run_cleanup_once()
        except Exception as exc:
            logger.error("[cleanup] 清理任务失败: {e}", e=exc, exc_info=True)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
    logger.info("[cleanup] 后台清理任务已停止")
