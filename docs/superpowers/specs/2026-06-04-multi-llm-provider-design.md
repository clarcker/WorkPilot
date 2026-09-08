# 多 LLM 提供商支持设计文档

## 1. 概述

### 1.1 设计目标

支持多种 LLM 提供商，允许用户通过环境变量配置选择使用 Ollama 本地模型或外部 API（如 DeepSeek）。

### 1.2 范围

- **聊天模型**：支持多提供商切换
- **Embedding 模型**：始终使用 Ollama（保持现有逻辑不变）
- **配置方式**：环境变量（.env 文件）
- **生效方式**：重启服务

## 2. 配置设计

### 2.1 新增配置字段

在 `backend/core/config.py` 的 `Settings` 类中添加：

```python
# LLM 提供商选择：ollama | openai_compatible
llm_provider: str = "ollama"

# Ollama 聊天模型配置
ollama_base_url: str = "http://ollama:11434"
ollama_chat_model: str = "qwen2.5:7b"

# OpenAI 兼容 API 配置（DeepSeek、Qwen-Max、vLLM 等）
openai_api_key: str = ""
openai_base_url: str = "https://api.deepseek.com/v1"
openai_model: str = "deepseek-chat"
```

### 2.2 配置说明

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `llm_provider` | str | `"ollama"` | 提供商选择：`ollama` 或 `openai_compatible` |
| `ollama_base_url` | str | `"http://ollama:11434"` | Ollama 服务地址 |
| `ollama_chat_model` | str | `"qwen2.5:7b"` | Ollama 聊天模型名称 |
| `openai_api_key` | str | `""` | OpenAI 兼容 API 密钥 |
| `openai_base_url` | str | `"https://api.deepseek.com/v1"` | API 基础 URL |
| `openai_model` | str | `"deepseek-chat"` | 模型名称 |

### 2.3 环境变量示例

```bash
# 使用 Ollama 本地模型
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_CHAT_MODEL=qwen2.5:7b

# 使用 DeepSeek API
LLM_PROVIDER=openai_compatible
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

### 2.4 移除的配置字段

移除旧的外部 LLM 配置（未使用）：
- ~~`external_llm_api_key`~~
- ~~`external_llm_base_url`~~
- ~~`external_llm_model`~~

## 3. 代码变更

### 3.1 新建 LLM 客户端模块

创建 `backend/services/llm_client.py`，统一封装 LLM 调用逻辑：

```python
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

    async with httpx.AsyncClient(timeout=120.0) as client:
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

    async with httpx.AsyncClient(timeout=120.0) as client:
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
```

### 3.2 修改 graph/nodes.py

将 `generate_answer_node` 中的 Ollama 直接调用改为使用 `llm_client`：

```python
# 旧代码（删除）
import httpx
url = f"{settings.ollama_base_url}/api/chat"
payload = {...}
async with httpx.AsyncClient(timeout=120.0) as client:
    async with client.stream("POST", url, json=payload) as response:
        ...

# 新代码
from services.llm_client import chat_stream

async for token in chat_stream(messages, temperature=0.3, max_tokens=2048):
    full_answer += token
    if queue:
        await queue.put({"type": "token", "content": token})
```

### 3.3 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/services/llm_client.py` | 新建 | 统一 LLM 客户端模块 |
| `backend/core/config.py` | 修改 | 添加 `llm_provider` 等配置，移除旧配置 |
| `backend/graph/nodes.py` | 修改 | 使用 `llm_client` 替代直接调用 |
| `backend/.env.example` | 修改 | 更新配置示例 |
| `backend/.env` | 修改 | 更新配置 |
| `backend/.env.test` | 修改 | 更新测试配置 |

## 4. 错误处理

| 场景 | 处理方式 |
|------|----------|
| 不支持的 provider 值 | 抛出 `ValueError`，启动时失败快速暴露 |
| API 密钥为空 | `openai_compatible` 模式下记录警告，请求会 401 |
| 网络超时 | 使用 120s 超时，超时后抛出异常 |
| API 返回错误 | 记录错误日志，返回用户友好提示 |

## 5. 测试验证

1. 配置 `LLM_PROVIDER=ollama`，验证本地模型调用正常
2. 配置 `LLM_PROVIDER=openai_compatible`，验证 DeepSeek API 调用正常
3. 验证流式输出在两种模式下都正常工作
4. 验证 Embedding 功能不受影响（始终使用 Ollama）
