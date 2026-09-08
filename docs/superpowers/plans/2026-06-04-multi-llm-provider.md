# 多 LLM 提供商支持 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 为 WorkPilot v2 后端添加多 LLM 提供商支持，允许通过环境变量配置选择 Ollama 本地模型或 OpenAI 兼容 API（如 DeepSeek）。

**Architecture:** 创建统一的 LLM 客户端模块 `services/llm_client.py`，根据 `settings.llm_provider` 配置选择不同的调用逻辑。聊天模型支持多提供商切换，Embedding 始终使用 Ollama。

**Tech Stack:** Python 3.11, FastAPI, httpx, loguru, pydantic-settings

---

## 文件结构

### 新建文件
| 文件 | 职责 |
|------|------|
| backend/services/llm_client.py | 统一 LLM 客户端模块，封装不同提供商的调用逻辑 |

### 修改文件
| 文件 | 职责 |
|------|------|
| backend/core/config.py | 添加 `llm_provider` 等新配置，移除旧配置 |
| backend/graph/nodes.py | 使用 `llm_client` 替代直接调用 Ollama |
| backend/.env.example | 更新配置示例 |
| backend/.env | 更新配置 |
| backend/.env.test | 更新测试配置 |

---

## Task 1: Update config.py with new LLM provider settings

**Files:** Modify `backend/core/config.py`

- [ ] **Step 1: Read current config.py**

```python
# Current Ollama config (keep):
ollama_base_url: str = "http://ollama:11434"
ollama_embed_model: str = "nomic-embed-text"
ollama_chat_model: str = "qwen2.5:7b"

# Current external LLM config (remove):
external_llm_api_key: str = ""
external_llm_base_url: str = "https://api.deepseek.com/v1"
external_llm_model: str = "deepseek-chat"
```

- [ ] **Step 2: Replace config fields**

```python
# LLM 提供商选择：ollama | openai_compatible
llm_provider: str = "ollama"

# Ollama 配置
ollama_base_url: str = "http://ollama:11434"
ollama_embed_model: str = "nomic-embed-text"
ollama_chat_model: str = "qwen2.5:7b"

# OpenAI 兼容 API 配置（DeepSeek、Qwen-Max、vLLM 等）
openai_api_key: str = ""
openai_base_url: str = "https://api.deepseek.com/v1"
openai_model: str = "deepseek-chat"
```

- [ ] **Step 3: Verify config loads correctly**

Run:
```bash
cd backend && python -c "from core.config import settings; print(f'provider={settings.llm_provider}, model={settings.openai_model}')"
```

Expected: `provider=ollama, model=deepseek-chat`

- [ ] **Step 4: Commit**

```bash
git add backend/core/config.py
git commit -m "feat: add multi-LLM provider config fields"
```

---

## Task 2: Create LLM client module

**Files:** Create `backend/services/llm_client.py`

- [ ] **Step 1: Create llm_client.py with chat_stream function**

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
```

- [ ] **Step 2: Add Ollama stream implementation**

```python
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
```

- [ ] **Step 3: Add OpenAI compatible stream implementation**

```python
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

- [ ] **Step 4: Verify module imports correctly**

Run:
```bash
cd backend && python -c "from services.llm_client import chat_stream; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/services/llm_client.py
git commit -m "feat: add unified LLM client module with Ollama and OpenAI support"
```

---

## Task 3: Update graph/nodes.py to use llm_client

**Files:** Modify `backend/graph/nodes.py`

- [ ] **Step 1: Read current generate_answer_node implementation**

Find the `generate_answer_node` function and locate the Ollama HTTP call.

- [ ] **Step 2: Add import for llm_client**

Add at top of file:
```python
from services.llm_client import chat_stream
```

- [ ] **Step 3: Replace Ollama direct call with llm_client**

Replace:
```python
import httpx

url = f"{settings.ollama_base_url}/api/chat"
payload = {
    "model":    settings.ollama_chat_model,
    "messages": messages,
    "stream":   True,
    "options":  {"temperature": 0.3, "num_predict": 2048},
}

try:
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
                    full_answer += token
                    if queue:
                        await queue.put({"type": "token", "content": token})

                if data.get("done"):
                    break

except httpx.HTTPError as exc:
    error_msg = f"模型调用失败：{exc}"
    logger.error(f"[generate_answer] {error_msg}")
    if queue:
        await queue.put({"type": "error", "content": error_msg})
        await queue.put(None)
    return {"full_answer": "", "sources": [], "error": error_msg}
```

With:
```python
try:
    async for token in chat_stream(messages, temperature=0.3, max_tokens=2048):
        full_answer += token
        if queue:
            await queue.put({"type": "token", "content": token})
except Exception as exc:
    error_msg = f"模型调用失败：{exc}"
    logger.error(f"[generate_answer] {error_msg}")
    if queue:
        await queue.put({"type": "error", "content": error_msg})
        await queue.put(None)
    return {"full_answer": "", "sources": [], "error": error_msg}
```

- [ ] **Step 4: Remove unused httpx import if no longer needed**

Check if `httpx` is used elsewhere in the file. If not, remove:
```python
import httpx
```

- [ ] **Step 5: Verify import works**

Run:
```bash
cd backend && python -c "from graph.nodes import generate_answer_node; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/graph/nodes.py
git commit -m "refactor: use llm_client in graph nodes instead of direct Ollama call"
```

---

## Task 4: Update .env files

**Files:** Modify `backend/.env.example`, `backend/.env`, `backend/.env.test`

- [ ] **Step 1: Update .env.example**

Add or update:
```bash
# ── LLM 提供商配置 ─────────────────────────────────────────────
# 可选值：ollama | openai_compatible
LLM_PROVIDER=ollama

# ── Ollama 配置 ─────────────────────────────────────────────────
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_CHAT_MODEL=qwen2.5:7b

# ── OpenAI 兼容 API 配置（DeepSeek、Qwen-Max 等）─────────────
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

Remove old external LLM config:
```bash
# Remove these:
EXTERNAL_LLM_API_KEY=
EXTERNAL_LLM_BASE_URL=
EXTERNAL_LLM_MODEL=
```

- [ ] **Step 2: Update .env**

Same changes as .env.example, but keep existing values if present.

- [ ] **Step 3: Update .env.test**

Add:
```bash
# LLM 提供商（测试时使用 Ollama）
LLM_PROVIDER=ollama
OPENAI_API_KEY=mock-key-for-testing
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

- [ ] **Step 4: Commit**

```bash
git add backend/.env.example backend/.env backend/.env.test
git commit -m "config: update .env files with new LLM provider settings"
```

---

## Task 5: Verify end-to-end

- [ ] **Step 1: Run unit tests**

```bash
cd backend && python -m pytest tests/unit/ -v -k "not database"
```

Expected: All non-database tests pass

- [ ] **Step 2: Verify imports**

```bash
cd backend && python -c "
from core.config import settings
from services.llm_client import chat_stream
from graph.nodes import generate_answer_node
print(f'provider={settings.llm_provider}')
print('All imports OK')
"
```

Expected:
```
provider=ollama
All imports OK
```

- [ ] **Step 3: Final commit if needed**

```bash
git add -A
git commit -m "feat: complete multi-LLM provider support"
```

---

## Self-Review Checklist

- [x] Every spec requirement has a corresponding task
- [x] No TBD/TODO placeholders
- [x] Type/method/property names consistent across tasks
- [x] Every step has complete code and commands
- [x] Every task has verification step
