"""P1 LLM 可靠性：熔断器 + 并发槽位 + 重试分类。

进程内状态即可（单 worker 内有效）；多 worker 各自熔断，行为一致。
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Optional

import httpx

from core.config import settings
from core.logger import logger

# SSE 排队事件（chat 节点注入 queue）
sse_queue_var: ContextVar[Optional[asyncio.Queue]] = ContextVar("sse_queue", default=None)
# 最近一次 LLM 调用的可靠性元信息（trace 用）
llm_meta_var: ContextVar[dict] = ContextVar("llm_meta", default={})


class CircuitState(str, Enum):
    closed = "closed"
    open = "open"
    half_open = "half_open"


class LLMBusyError(RuntimeError):
    """并发槽位等待超时。"""


class LLMUnavailableError(RuntimeError):
    """所有 provider 均不可用。"""


def is_retryable_exc(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.WriteError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    if isinstance(exc, (asyncio.TimeoutError, ConnectionError)):
        return True
    return False


@dataclass
class CircuitBreaker:
    provider: str
    fail_threshold: int = 5
    open_seconds: float = 30.0
    state: CircuitState = CircuitState.closed
    fail_count: int = 0
    opened_at: float = 0.0
    probe_in_flight: bool = False

    def allow(self) -> bool:
        now = time.monotonic()
        if self.state == CircuitState.closed:
            return True
        if self.state == CircuitState.open:
            if now - self.opened_at >= self.open_seconds:
                self.state = CircuitState.half_open
                self.probe_in_flight = False
                logger.info(f"[llm-circuit] {self.provider} → half_open")
                return True
            return False
        # half_open：只放一个探测
        if self.probe_in_flight:
            return False
        return True

    def on_success(self) -> None:
        if self.state != CircuitState.closed:
            logger.info(f"[llm-circuit] {self.provider} → closed (recovered)")
        self.state = CircuitState.closed
        self.fail_count = 0
        self.probe_in_flight = False

    def on_failure(self) -> None:
        self.fail_count += 1
        if self.state == CircuitState.half_open:
            self.state = CircuitState.open
            self.opened_at = time.monotonic()
            self.probe_in_flight = False
            logger.warning(f"[llm-circuit] {self.provider} half_open 探测失败 → open")
            return
        if self.fail_count >= self.fail_threshold:
            self.state = CircuitState.open
            self.opened_at = time.monotonic()
            logger.warning(
                f"[llm-circuit] {self.provider} 连续失败 {self.fail_count} 次 → open "
                f"({self.open_seconds}s 后 half-open)"
            )

    def mark_probe(self) -> None:
        if self.state == CircuitState.half_open:
            self.probe_in_flight = True


_breakers: dict[str, CircuitBreaker] = {}
_sems: dict[str, asyncio.Semaphore] = {}
_waiting = 0


def get_breaker(provider: str) -> CircuitBreaker:
    if provider not in _breakers:
        _breakers[provider] = CircuitBreaker(
            provider=provider,
            fail_threshold=settings.llm_circuit_fail_threshold,
            open_seconds=settings.llm_circuit_open_seconds,
        )
    b = _breakers[provider]
    b.fail_threshold = settings.llm_circuit_fail_threshold
    b.open_seconds = settings.llm_circuit_open_seconds
    return b


def circuit_state(provider: str) -> str:
    return get_breaker(provider).state.value


def _get_sem(provider: str) -> asyncio.Semaphore:
    limit = (
        settings.llm_max_concurrency_external
        if provider == "openai_compatible"
        else settings.llm_max_concurrency_local
    )
    limit = max(1, limit)
    cache_key = f"{provider}|{limit}"
    cached = _sems.get(cache_key)
    if cached is None:
        cached = asyncio.Semaphore(limit)
        _sems[cache_key] = cached
    return cached


async def _notify_queued(position: int) -> None:
    q = sse_queue_var.get()
    if q is None:
        return
    try:
        await q.put({"type": "queued", "content": {"position": position}})
    except Exception:
        pass


@asynccontextmanager
async def llm_slot(provider: str) -> AsyncIterator[str]:
    """并发槽位：等待超时抛 LLMBusyError；等待时推 SSE queued。"""
    global _waiting
    sem = _get_sem(provider)
    if sem.locked():
        _waiting += 1
        try:
            await _notify_queued(_waiting)
        except Exception:
            pass
    acquired = False
    try:
        try:
            await asyncio.wait_for(sem.acquire(), timeout=settings.llm_queue_timeout)
            acquired = True
        except (asyncio.TimeoutError, TimeoutError):
            raise LLMBusyError("系统繁忙，请稍后再试") from None
        yield provider
    finally:
        if acquired:
            sem.release()
        if sem.locked():
            _waiting = max(0, _waiting - 1)


async def call_with_resilience(
    provider: str,
    factory,  # callable(provider) -> awaitable result
    *,
    allow_fallback: bool = True,
    queue: asyncio.Queue | None = None,
) -> tuple[Any, dict]:
    """
    执行一次 LLM 调用：熔断检查 → 并发槽位 → 重试 → 失败记账 → 可选降级。

    Returns:
        (result, meta) meta 含 circuit_state / fallback_provider / retries
    """
    if queue is not None:
        token_q = sse_queue_var.set(queue)
    else:
        token_q = None
    meta: dict = {
        "provider": provider,
        "circuit_state": circuit_state(provider),
        "fallback_provider": None,
        "retries": 0,
    }
    try:
        target = provider
        breaker = get_breaker(target)
        if not breaker.allow():
            if allow_fallback and target == "openai_compatible" and settings.llm_fallback_enabled:
                meta["fallback_provider"] = "ollama"
                meta["circuit_state"] = circuit_state(target)
                target = "ollama"
                breaker = get_breaker(target)
                if not breaker.allow():
                    raise LLMUnavailableError("模型服务暂不可用（本地与外部均熔断）")
                logger.warning("[llm] external circuit open → fallback ollama")
            else:
                raise LLMUnavailableError(f"模型服务 {target} 熔断中，请稍后再试")

        breaker.mark_probe()
        last_exc: BaseException | None = None
        max_try = max(1, settings.llm_retry_max)
        async with llm_slot(target):
            for attempt in range(max_try):
                try:
                    result = await factory(target)
                    breaker.on_success()
                    meta["provider"] = target
                    meta["circuit_state"] = circuit_state(target)
                    meta["retries"] = attempt
                    return result, meta
                except Exception as exc:
                    last_exc = exc
                    breaker.on_failure()
                    if not is_retryable_exc(exc):
                        meta["circuit_state"] = circuit_state(target)
                        raise
                    if attempt < max_try - 1:
                        delay = settings.llm_retry_base_delay * (2 ** attempt)
                        logger.warning(
                            f"[llm] {target} attempt {attempt + 1}/{max_try} 失败，{delay}s 后重试: "
                            f"{type(exc).__name__}"
                        )
                        await asyncio.sleep(delay)
                        meta["retries"] = attempt + 1
                    else:
                        meta["circuit_state"] = circuit_state(target)

        # 重试耗尽：若外部失败且允许降级 → 本地
        if (
            allow_fallback
            and target == "openai_compatible"
            and settings.llm_fallback_enabled
            and meta.get("fallback_provider") is None
        ):
            logger.warning("[llm] external 重试耗尽 → fallback ollama")
            meta["fallback_provider"] = "ollama"
            alt = get_breaker("ollama")
            if alt.allow():
                alt.mark_probe()
                try:
                    async with llm_slot("ollama"):
                        result = await factory("ollama")
                    alt.on_success()
                    meta["provider"] = "ollama"
                    meta["circuit_state"] = circuit_state("ollama")
                    return result, meta
                except Exception as exc:
                    alt.on_failure()
                    last_exc = exc
                    meta["circuit_state"] = circuit_state("ollama")
        raise last_exc or LLMUnavailableError("模型调用失败")
    finally:
        if token_q is not None:
            sse_queue_var.reset(token_q)
        # 写回 contextvar 供 trace 读取
        try:
            current = dict(llm_meta_var.get() or {})
            current.update(meta)
            llm_meta_var.set(current)
        except Exception:
            pass


def reset_circuits_for_tests() -> None:
    _breakers.clear()
    _sems.clear()
