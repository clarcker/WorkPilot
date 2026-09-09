"""
LLM 客户端服务：统一封装不同提供商的聊天模型调用。

支持：
- Ollama 本地模型（/api/chat）
- OpenAI 兼容 API（/v1/chat/completions）
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from core.config import settings
from core.logger import logger


def _complete_timeout() -> httpx.Timeout:
    """非流式调用：建连要快，读取要容忍慢机器上的 prefill。"""
    return httpx.Timeout(
        connect=settings.llm_connect_timeout,
        read=settings.llm_complete_timeout,
        write=settings.llm_connect_timeout,
        pool=settings.llm_connect_timeout,
    )


def _stream_timeout() -> httpx.Timeout:
    """
    流式调用：read 是"两次数据之间的最大间隔"，而不是整体耗时上限。

    首个 token 之前的 prefill 全部算在这一个间隔里——纯 CPU 上带上下文的
    7B 模型经常超过 120s，之前就是在这里被误杀成一个内容为空的
    httpx.ReadTimeout，日志里只留下一句"模型调用失败："。
    """
    return httpx.Timeout(
        connect=settings.llm_connect_timeout,
        read=settings.llm_stream_timeout,
        write=settings.llm_connect_timeout,
        pool=settings.llm_connect_timeout,
    )


async def chat_complete(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 256,
) -> str:
    """
    非流式调用 LLM，返回完整回复字符串。

    Args:
        messages: 消息列表，格式 [{"role": "user", "content": "..."}]
        temperature: 温度参数
        max_tokens: 最大生成 token 数

    Returns:
        模型生成的完整文本
    """
    provider = settings.llm_provider

    if provider == "ollama":
        return await _ollama_complete(messages, temperature, max_tokens)
    elif provider == "openai_compatible":
        return await _openai_complete(messages, temperature, max_tokens)
    else:
        raise ValueError(f"不支持的 LLM 提供商: {provider}")


async def _ollama_complete(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    """Ollama 非流式调用"""
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


async def _openai_complete(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    """OpenAI 兼容 API 非流式调用"""
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
    logger.info("LLM call | provider=openai_compatible (complete) | model={model}", model=settings.openai_model)
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
) -> AsyncIterator[str]:
    """
    流式调用 LLM 聊天接口。

    Args:
        messages: 消息列表，格式 [{"role": "user", "content": "..."}]
        temperature: 温度参数
        max_tokens: 最大生成 token 数

    Yields:
        模型生成的 token 字符串
    """
    provider = settings.llm_provider

    if provider == "ollama":
        async for token in _ollama_stream(messages, temperature, max_tokens):
            yield token
    elif provider == "openai_compatible":
        async for token in _openai_stream(messages, temperature, max_tokens):
            yield token
    else:
        raise ValueError(f"不支持的 LLM 提供商: {provider}")


async def _ollama_stream(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> AsyncIterator[str]:
    """Ollama 流式调用"""
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
    """OpenAI 兼容 API 流式调用"""
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

    logger.info("LLM call | provider=openai_compatible | model={model}", model=settings.openai_model)

    async with httpx.AsyncClient(timeout=_stream_timeout()) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for raw_line in response.aiter_lines():
                if not raw_line:
                    continue
                # 跳过 SSE 前缀
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
