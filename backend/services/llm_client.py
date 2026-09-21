"""
LLM 客户端服务：统一封装不同提供商的聊天模型调用。

P1 可靠性（经 llm_resilience）：
- 指数退避重试（超时/连接/429/5xx）
- 每 provider 熔断；openai 熔断时降级 ollama（反向不降级）
- 并发 Semaphore + 排队 SSE queued；超时 LLMBusyError
- 流式：首 token 前可重试，首 token 后不重试
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from core.anonymizer import anonymize_messages
from core.config import maybe_reload_settings, settings
from core.logger import logger
from services.llm_resilience import (
    LLMBusyError,
    LLMUnavailableError,
    call_with_resilience,
    circuit_state,
    is_retryable_exc,
    llm_meta_var,
    sse_queue_var,
)

_ADMIN_ROLES = frozenset({"super_admin", "dept_admin"})


def resolve_provider(user_role: str | None = None) -> str:
    """按角色解析实际使用的 LLM 提供商。每次调用前检查配置文件是否变更。"""
    maybe_reload_settings()
    if (
        user_role in _ADMIN_ROLES
        and settings.admin_use_external_llm
        and settings.openai_api_key
        and settings.openai_api_key.strip()
    ):
        return "openai_compatible"
    return settings.llm_provider


def should_anonymize_for_llm(user_role: str | None = None) -> bool:
    """只有真正出网到外部 API 时才需要脱敏。"""
    return resolve_provider(user_role) == "openai_compatible"


def _complete_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.llm_connect_timeout,
        read=settings.llm_complete_timeout,
        write=settings.llm_connect_timeout,
        pool=settings.llm_connect_timeout,
    )


def _stream_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.llm_connect_timeout,
        read=settings.llm_stream_timeout,
        write=settings.llm_connect_timeout,
        pool=settings.llm_connect_timeout,
    )


def _prepare_outbound(messages: list[dict], provider: str) -> list[dict]:
    if provider == "openai_compatible":
        return anonymize_messages(messages)
    return messages


def _factory_complete(provider: str, messages: list[dict], temperature: float, max_tokens: int):
    async def _call(prov: str) -> str:
        msgs = _prepare_outbound(messages, prov)
        if prov == "ollama":
            return await _ollama_complete(msgs, temperature, max_tokens)
        return await _openai_complete(msgs, temperature, max_tokens)

    return _call


async def chat_complete(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 256,
    user_role: str | None = None,
    queue: asyncio.Queue | None = None,
) -> str:
    provider = resolve_provider(user_role)
    factory = _factory_complete(provider, messages, temperature, max_tokens)
    q = queue if queue is not None else sse_queue_var.get()
    result, meta = await call_with_resilience(provider, factory, queue=q)
    return result


async def _ollama_complete(messages: list[dict], temperature: float, max_tokens: int) -> str:
    url = f"{settings.ollama_base_url}/api/chat"
    payload = {
        "model": settings.ollama_chat_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    logger.info("LLM call | provider=ollama (complete) | model={model}", model=settings.ollama_chat_model)
    async with httpx.AsyncClient(timeout=_complete_timeout()) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "").strip()


async def _openai_complete(messages: list[dict], temperature: float, max_tokens: int) -> str:
    url = f"{settings.openai_base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.openai_api_key}",
    }
    payload = {
        "model": settings.openai_model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    logger.info(
        "LLM call | provider=openai_compatible (complete) | model={model} | base={base}",
        model=settings.openai_model, base=settings.openai_base_url,
    )
    async with httpx.AsyncClient(timeout=_complete_timeout()) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
        return ""


async def chat_stream(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
    user_role: str | None = None,
    queue: asyncio.Queue | None = None,
) -> AsyncIterator[str]:
    """
    流式调用。首 token 之前允许重试/降级；首 token 之后不重试。
    """
    provider = resolve_provider(user_role)
    q = queue if queue is not None else sse_queue_var.get()
    if q is not None:
        sse_queue_var.set(q)

    meta = {
        "provider": provider,
        "circuit_state": circuit_state(provider),
        "fallback_provider": None,
        "retries": 0,
    }
    providers_try = [provider]
    if (
        provider == "openai_compatible"
        and settings.llm_fallback_enabled
        and settings.openai_api_key
    ):
        providers_try.append("ollama")

    last_exc: BaseException | None = None
    max_try = max(1, settings.llm_retry_max)

    for prov in providers_try:
        from services.llm_resilience import get_breaker
        breaker = get_breaker(prov)
        if not breaker.allow():
            meta["circuit_state"] = circuit_state(prov)
            if prov != providers_try[-1]:
                meta["fallback_provider"] = providers_try[providers_try.index(prov) + 1]
                continue
            raise LLMUnavailableError(f"模型服务 {prov} 熔断中")

        breaker.mark_probe()
        for attempt in range(max_try):
            try:
                from services.llm_resilience import llm_slot
                async with llm_slot(prov):
                    got_first = False
                    async for token in _stream_once(prov, messages, temperature, max_tokens):
                        if not got_first:
                            breaker.on_success()
                            got_first = True
                            meta["provider"] = prov
                            meta["retries"] = attempt
                            if prov != provider:
                                meta["fallback_provider"] = prov
                            meta["circuit_state"] = circuit_state(prov)
                            try:
                                cur = dict(llm_meta_var.get() or {})
                                cur.update(meta)
                                llm_meta_var.set(cur)
                            except Exception:
                                pass
                        yield token
                    if not got_first:
                        # 空流视为失败
                        raise httpx.ReadError("empty stream")
                    return
            except LLMBusyError:
                raise
            except Exception as exc:
                last_exc = exc
                # 首 token 后失败：不重试，直接抛给上层
                if not is_retryable_exc(exc):
                    breaker.on_failure()
                    meta["circuit_state"] = circuit_state(prov)
                    if prov != providers_try[-1]:
                        break  # 尝试下一 provider
                    raise
                # 首 token 前：可重试
                if attempt < max_try - 1:
                    delay = settings.llm_retry_base_delay * (2 ** attempt)
                    logger.warning(
                        f"[llm-stream] {prov} attempt {attempt+1} 失败（首 token 前），{delay}s 重试: "
                        f"{type(exc).__name__}"
                    )
                    await asyncio.sleep(delay)
                    meta["retries"] = attempt + 1
                else:
                    breaker.on_failure()
                    meta["circuit_state"] = circuit_state(prov)
                    if prov != providers_try[-1]:
                        meta["fallback_provider"] = providers_try[providers_try.index(prov) + 1]
                        break
    try:
        cur = dict(llm_meta_var.get() or {})
        cur.update(meta)
        llm_meta_var.set(cur)
    except Exception:
        pass
    raise last_exc or LLMUnavailableError("模型调用失败")


async def _stream_once(
    provider: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    msgs = _prepare_outbound(messages, provider)
    if provider == "ollama":
        async for t in _ollama_stream(msgs, temperature, max_tokens):
            yield t
    else:
        async for t in _openai_stream(msgs, temperature, max_tokens):
            yield t


async def _ollama_stream(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    url = f"{settings.ollama_base_url}/api/chat"
    payload = {
        "model": settings.ollama_chat_model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    logger.info("LLM call | provider=ollama | model={model}", model=settings.ollama_chat_model)
    async with httpx.AsyncClient(timeout=_stream_timeout()) as client:
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for raw_line in response.aiter_lines():
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                token = data.get("message", {}).get("content", "")
                if token:
                    yield token
                if data.get("done"):
                    break


async def _openai_stream(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    url = f"{settings.openai_base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.openai_api_key}",
    }
    payload = {
        "model": settings.openai_model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    logger.info(
        "LLM call | provider=openai_compatible | model={model} | base={base}",
        model=settings.openai_model, base=settings.openai_base_url,
    )
    async with httpx.AsyncClient(timeout=_stream_timeout()) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for raw_line in response.aiter_lines():
                if not raw_line:
                    continue
                if raw_line.startswith("data: "):
                    raw_line = raw_line[6:]
                if raw_line.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        yield token
