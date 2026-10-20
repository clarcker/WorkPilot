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


async def get_active_embed_model() -> str:
    """P5：优先 system_config.active_embedding_model，否则配置默认。"""
    try:
        from sqlalchemy import select
        from db.models import SystemConfig
        from db.session import async_session_factory
        async with async_session_factory() as db:
            row = await db.scalar(
                select(SystemConfig).where(SystemConfig.key == "active_embedding_model")
            )
            if row and isinstance(row.value, dict) and row.value.get("model"):
                return str(row.value["model"])
    except Exception:
        pass
    return settings.ollama_embed_model


async def get_embeddings_batch(
    texts: list[str],
    model: str | None = None,
) -> list[list[float]]:
    if not texts:
        return []

    model_name = model or await get_active_embed_model()
    all_embeddings: list[list[float]] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i: i + _BATCH_SIZE]
            embeddings = await _embed_batch(client, batch, model_name)
            all_embeddings.extend(embeddings)

    if len(all_embeddings) != len(texts):
        raise ValueError(
            f"Embedding 数量不匹配：期望 {len(texts)}，实际 {len(all_embeddings)}"
        )

    return all_embeddings


async def get_embedding(text: str, model: str | None = None) -> list[float]:
    """单条 embedding，内部复用批量接口。"""
    results = await get_embeddings_batch([text], model=model)
    return results[0]


# ------------------------------------------------------------------
# 内部实现
# ------------------------------------------------------------------

async def _embed_batch(
    client: httpx.AsyncClient,
    texts: list[str],
    model: str | None = None,
) -> list[list[float]]:
    model_name = model or settings.ollama_embed_model
    try:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": model_name, "input": texts},
        )
        if resp.status_code == 404:
            return await _embed_one_by_one(client, texts, model_name)
        resp.raise_for_status()
        data = resp.json()
        return data["embeddings"]

    except httpx.HTTPStatusError:
        raise
    except Exception as e:
        logger.warning(f"批量 embedding 失败，回退到逐条模式: {e}")
        return await _embed_one_by_one(client, texts, model_name)


async def _embed_one_by_one(
    client: httpx.AsyncClient,
    texts: list[str],
    model: str | None = None,
) -> list[list[float]]:
    model_name = model or settings.ollama_embed_model
    results = []
    for text in texts:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/embeddings",
            json={"model": model_name, "prompt": text},
        )
        resp.raise_for_status()
        results.append(resp.json()["embedding"])
    return results
