"""Loguru 日志配置模块

提供统一的日志配置，支持：
- 按天轮转日志文件
- 自动删除过期日志
- 请求追踪（request_id, user_id）
- 开发/生产模式切换
- FastAPI 请求日志中间件
"""

import sys
import uuid
from contextvars import ContextVar
from pathlib import Path

from loguru import logger

# 请求追踪上下文变量
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")


def setup_logger(
    log_dir: str = "logs",
    log_level: str = "DEBUG",
    log_rotation: str = "1 day",
    log_retention: str = "7 days",
    log_console: bool = True,
    environment: str = "development",
) -> None:
    """配置 loguru 日志系统

    Args:
        log_dir: 日志文件目录
        log_level: 日志级别
        log_rotation: 日志轮转周期
        log_retention: 日志保留时间
        log_console: 是否输出到控制台
        environment: 运行环境 (development/production)
    """
    # 移除默认处理器
    logger.remove()

    # 日志格式
    log_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "{name}:{function}:{line} | "
        "req_id={extra[request_id]} | "
        "user_id={extra[user_id]} | "
        "{message}"
    )

    # 确保日志目录存在
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 文件输出 - 所有级别
    logger.add(
        str(log_path / "workpilot_{time:YYYY-MM-DD}.log"),
        format=log_format,
        level=log_level,
        rotation=log_rotation,
        retention=log_retention,
        encoding="utf-8",
        enqueue=True,  # 异步写入
    )

    # 控制台输出
    if log_console:
        if environment == "development":
            # 开发模式：显示所有级别
            logger.add(
                sys.stderr,
                format=log_format,
                level=log_level,
                colorize=True,
            )
        else:
            # 生产模式：只显示 WARNING 及以上
            logger.add(
                sys.stderr,
                format=log_format,
                level="WARNING",
                colorize=True,
            )

    # 绑定默认上下文变量
    logger.configure(
        extra={"request_id": "-", "user_id": "-"}
    )

    logger.info(
        "Logger initialized | level={level} | env={env} | dir={dir}",
        level=log_level,
        env=environment,
        dir=log_dir,
    )


def get_logger_with_context(request_id: str = "-", user_id: str = "-"):
    """获取带有请求上下文的 logger 实例"""
    return logger.bind(request_id=request_id, user_id=user_id)


def generate_request_id() -> str:
    """生成唯一请求 ID"""
    return str(uuid.uuid4())[:8]


# 导出 logger 供其他模块使用
__all__ = [
    "logger",
    "setup_logger",
    "get_logger_with_context",
    "generate_request_id",
    "request_id_var",
    "user_id_var",
    "RequestLoggingMiddleware",
]


# RequestLoggingMiddleware 需要 Starlette，延迟导入避免循环依赖
class RequestLoggingMiddleware:
    """FastAPI 请求日志中间件

    为每个请求生成唯一 request_id，并记录请求/响应信息。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request

        request = Request(scope, receive)
        request_id = request.headers.get("X-Request-ID") or generate_request_id()

        # 设置上下文变量
        request_id_var.set(request_id)
        logger.bind(request_id=request_id)

        # 记录请求开始
        logger.info(
            "Request started | {method} {path} | client={client}",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "-",
        )

        # 处理请求
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # 在响应头中添加 request_id
                headers = message.get("headers", [])
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

