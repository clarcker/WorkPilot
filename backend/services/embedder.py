"""
Embedding 服务：调用 Ollama 接口为文本生成向量。

- 模型：nomic-embed-text（768 维，CPU 可运行）
- 接口：POST /api/embeddings（旧版兼容接口）
        POST /api/embed        （新版批量接口）
- 优先使用批量接口 /api/embed，回退到逐条 /api/embeddings

关键约束（来自 系统架构.md）：
  文档向量化和查询向量化必须使用同一个模型，
  切换模型时需要重新向量化所有文档。
"""
from __future__ import annotations

import httpx

from core.config import settings
from core.logger import logger

# 批量最大条数（防止单次请求过大）
_BATCH_SIZE = 16


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    批量获取 embedding 向量。

    Args:
        texts: 待向量化的文本列表

    Returns:
        与 texts 等长的向量列表，每个向量为 768 维 float 列表。

    Raises:
        httpx.HTTPError: Ollama 服务不可达或返回非 200
        ValueError: 返回向量数量与输入不匹配
    """
    if not texts:
        return []

    all_embeddings: list[list[float]] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 按批次处理
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i: i + _BATCH_SIZE]
            embeddings = await _embed_batch(client, batch)
            all_embeddings.extend(embeddings)

    if len(all_embeddings) != len(texts):
        raise ValueError(
            f"Embedding 数量不匹配：期望 {len(texts)}，实际 {len(all_embeddings)}"
        )

    return all_embeddings


async def get_embedding(text: str) -> list[float]:
    """单条 embedding，内部复用批量接口。"""
    results = await get_embeddings_batch([text])
    return results[0]


# ------------------------------------------------------------------
# 内部实现
# ------------------------------------------------------------------

async def _embed_batch(client: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
    """
    尝试新版批量接口 /api/embed；若返回 404 则逐条调用旧版接口 /api/embeddings。
    """
    try:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": settings.ollama_embed_model, "input": texts},
        )
        if resp.status_code == 404:
            # 旧版 Ollama 不支持 /api/embed，回退到逐条调用
            return await _embed_one_by_one(client, texts)
        resp.raise_for_status()
        data = resp.json()
        # 新版响应格式：{"embeddings": [[...]]}
        return data["embeddings"]

    except httpx.HTTPStatusError:
        raise
    except Exception as e:
        logger.warning(f"批量 embedding 失败，回退到逐条模式: {e}")
        return await _embed_one_by_one(client, texts)


async def _embed_one_by_one(
    client: httpx.AsyncClient, texts: list[str]
) -> list[list[float]]:
    """旧版 Ollama /api/embeddings 逐条调用。"""
    results = []
    for text in texts:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/embeddings",
            json={"model": settings.ollama_embed_model, "prompt": text},
        )
        resp.raise_for_status()
        results.append(resp.json()["embedding"])
    return results
