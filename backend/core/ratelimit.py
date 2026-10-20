"""
简单内存滑动窗口限流中间件。

适用：单机/开发。多 Worker 生产应换 Redis 令牌桶（见 系统架构.md）。

默认策略：
- /api/auth/login          每 IP 10 次/分钟
- /api/chat/stream         每用户 20 次/5 分钟
- 其他 /api/*              不限流
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from core.logger import logger


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        login_per_minute: int = 10,
        chat_per_5min: int = 20,
    ) -> None:
        super().__init__(app)
        self.login_limit = login_per_minute
        self.login_window = 60.0
        self.chat_limit = chat_per_5min
        self.chat_window = 300.0
        # key -> deque[timestamp]
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        # 优先用户身份（JWT 在后续依赖里解析，中间件层用 IP 兜底）
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        client = self._client_key(request)

        if path.endswith("/api/auth/login") or path == "/api/auth/login":
            key = f"login:{client}"
            if not self._allow(key, self.login_limit, self.login_window):
                logger.warning("[ratelimit] login blocked | ip={ip}", ip=client)
                return JSONResponse(
                    status_code=429,
                    content={"code": 42901, "data": None, "message": "登录尝试过于频繁，请稍后再试"},
                )
        elif "/api/chat/stream" in path:
            # 有 JWT 时用 token 前缀区分用户，避免共享出口 IP 误伤
            auth = request.headers.get("Authorization", "")
            user_key = auth[-24:] if len(auth) > 24 else client
            key = f"chat:{user_key}"
            if not self._allow(key, self.chat_limit, self.chat_window):
                logger.warning("[ratelimit] chat blocked | key={k}", k=key[:16])
                return JSONResponse(
                    status_code=429,
                    content={"code": 42902, "data": None, "message": "对话请求过于频繁，请稍后再试"},
                )

        return await call_next(request)
