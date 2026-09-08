"""
系统配置路由（仅超级管理员可操作）

GET   /api/admin/system/config        — 获取所有可配置项（含默认值兜底）
PATCH /api/admin/system/config/{key}  — 更新单个配置项
GET   /api/admin/system/logs          — 读取运行日志文件
"""
import re
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import AuditAction, write_audit
from core.config import settings
from core.deps import require_super_admin
from core.logger import logger
from db.models import SystemConfig, User
from db.session import get_db
from schemas.common import BaseResp

router = APIRouter()

# 允许通过 API 修改的配置键白名单及类型说明
_ALLOWED_KEYS: dict[str, dict] = {
    "max_conversations_per_user":    {"default": 200,  "label": "每用户最大会话数"},
    "max_messages_per_conversation": {"default": 500,  "label": "每会话最大消息数"},
    "archive_retention_days":        {"default": 180,  "label": "归档数据保留天数"},
}


class ConfigPatchBody(BaseModel):
    value: Any


def _get_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.get("/config", response_model=BaseResp)
async def get_all_config(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    rows = (await db.execute(select(SystemConfig))).scalars().all()
    stored = {row.key: row.value for row in rows}

    result = {}
    for key, meta in _ALLOWED_KEYS.items():
        stored_val = stored.get(key)
        if stored_val is None:
            val = meta["default"]
        elif isinstance(stored_val, dict) and "value" in stored_val:
            val = stored_val["value"]
        elif isinstance(stored_val, (int, float)):
            val = stored_val
        else:
            val = meta["default"]
        result[key] = {
            "value": val,
            "label": meta["label"],
            "default": meta["default"],
        }

    return BaseResp.ok(data=result)


@router.patch("/config/{key}", response_model=BaseResp)
async def update_config(
    key: str,
    body: ConfigPatchBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    if key not in _ALLOWED_KEYS:
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "message": f"不支持的配置项: {key}"},
        )
    if not isinstance(body.value, int) or body.value <= 0:
        raise HTTPException(
            status_code=422,
            detail={"code": 42201, "message": "配置值必须为正整数"},
        )

    existing = await db.get(SystemConfig, key)
    old_value = existing.value if existing else None

    if existing:
        existing.value = {"value": body.value}
        existing.updated_by = current_user.id
    else:
        db.add(SystemConfig(
            key=key,
            value={"value": body.value},
            updated_by=current_user.id,
        ))

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.SYSTEM_CONFIG,
        resource_type="system_config",
        resource_id=key,
        old_value=old_value,
        new_value={"value": body.value},
        ip_address=_get_ip(request),
    )

    logger.info("System config updated | key={key} | value={value} | by={operator}", key=key, value=body.value, operator=current_user.username)

    return BaseResp.ok(data={"key": key, "value": body.value})


# ------------------------------------------------------------------
# GET /logs   读取运行日志文件
# ------------------------------------------------------------------

# 日志行格式：2026-06-04 17:30:12.345 | INFO     | module:func:line | req_id=xxx | user_id=xxx | message
_LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \| (\w+)\s*\| (.+)$"
)


def _parse_log_line(line: str) -> dict | None:
    """解析一行日志，返回结构化数据或 None。"""
    m = _LOG_LINE_RE.match(line.strip())
    if not m:
        return None
    timestamp, level, rest = m.group(1), m.group(2), m.group(3)
    # 尝试拆分 module:func:line | req_id=... | user_id=... | message
    parts = rest.split(" | ", 3)
    location = parts[0] if len(parts) > 0 else ""
    req_id = ""
    user_id = ""
    message = ""
    for p in parts[1:]:
        if p.startswith("req_id="):
            req_id = p[7:]
        elif p.startswith("user_id="):
            user_id = p[8:]
        else:
            message = p
    if not message and not req_id and not user_id:
        # 可能是旧格式，直接把 rest 当 message
        message = rest
    return {
        "timestamp": timestamp,
        "level": level,
        "location": location,
        "request_id": req_id,
        "user_id": user_id,
        "message": message,
    }


@router.get("/logs", response_model=BaseResp)
async def get_logs(
    log_date: str = Query(default=None, description="日期 YYYY-MM-DD，默认今天"),
    level: str = Query(default=None, description="日志级别过滤：DEBUG/INFO/WARNING/ERROR/CRITICAL"),
    keyword: str = Query(default=None, max_length=200, description="关键词搜索"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_super_admin),
):
    """读取指定日期的日志文件，支持级别过滤和关键词搜索。"""
    # 确定日期
    if log_date:
        try:
            target_date = date.fromisoformat(log_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={"code": 40001, "message": "日期格式错误，应为 YYYY-MM-DD"},
            )
    else:
        target_date = date.today()

    # 构建日志文件路径
    log_dir = Path(settings.log_dir)
    log_file = log_dir / f"workpilot_{target_date.isoformat()}.log"

    if not log_file.exists():
        return BaseResp.ok(data={
            "date": target_date.isoformat(),
            "file_exists": False,
            "total": 0,
            "page": page,
            "page_size": page_size,
            "items": [],
        })

    # 读取并解析日志文件
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"Failed to read log file: {e}")
        raise HTTPException(
            status_code=500,
            detail={"code": 50001, "message": "读取日志文件失败"},
        )

    # 解析并过滤
    entries = []
    for line in lines:
        parsed = _parse_log_line(line)
        if not parsed:
            continue

        # 级别过滤
        if level and parsed["level"].upper() != level.upper():
            continue

        # 关键词搜索
        if keyword and keyword.lower() not in line.lower():
            continue

        entries.append(parsed)

    # 翻转顺序（最新的在前）
    entries.reverse()

    # 分页
    total = len(entries)
    start = (page - 1) * page_size
    end = start + page_size
    items = entries[start:end]

    return BaseResp.ok(data={
        "date": target_date.isoformat(),
        "file_exists": True,
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    })
