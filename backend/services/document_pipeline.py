"""
文档处理流水线：解析 → 分块 → 向量化 → 入库。

由 api/documents.py 中的上传接口通过 BackgroundTasks 异步触发，
也可由 /reindex 接口重新触发（幂等：先清除旧数据再重建）。

流程：
  1. 从数据库加载 Document 记录
  2. 调用 document_parser 解析文件 → TextSegment 列表
  3. 调用 chunker 分块 → ChunkData 列表
  4. 删除该文档旧的 doc_chunks（及级联的 embeddings）
  5. 保存新 doc_chunks，批量调用 Ollama 获取 embedding 并保存
  6. 更新 Document.status = "ready"

任何步骤失败 → 在独立 Session 中将 Document.status 置为 "failed" 并记录 error_message。
"""
from __future__ import annotations

from sqlalchemy import delete

from core.config import settings
from core.logger import logger
from db.models import DocChunk, DocStatus, Document, Embedding
from db.session import async_session_factory
from services.chunker import chunk_segments
from services.document_parser import parse_document
from services.embedder import get_embeddings_batch


async def run_pipeline(doc_id: int) -> None:
    """
    触发文档处理流水线的入口函数，供 BackgroundTasks 调用。

    Args:
        doc_id: documents 表主键
    """
    try:
        await _process(doc_id)
        logger.info(f"[pipeline] doc_id={doc_id} 处理完成")
    except Exception as exc:
        logger.error(f"[pipeline] doc_id={doc_id} 处理失败: {exc}", exc_info=True)
        await _mark_failed(doc_id, str(exc))


# ------------------------------------------------------------------
# 核心处理逻辑
# ------------------------------------------------------------------

async def _process(doc_id: int) -> None:
    async with async_session_factory() as db:
        # 1. 加载文档
        doc: Document | None = await db.get(Document, doc_id)
        if not doc:
            logger.warning(f"[pipeline] doc_id={doc_id} 不存在，跳过")
            return

        # 确保状态为 processing
        doc.status = DocStatus.processing
        doc.error_message = None
        await db.flush()
        logger.info(f"[pipeline] doc_id={doc_id} 状态设为 processing")

        # 2. 解析文件
        try:
            segments = parse_document(doc.storage_path, doc.file_type)
        except ValueError as e:
            raise ValueError(f"文件解析失败：{e}")
        except Exception as e:
            raise ValueError(f"文件解析异常：{e}")
        if not segments:
            raise ValueError("文件解析结果为空，请检查文件内容")
        logger.info(f"[pipeline] doc_id={doc_id} 解析完成，segments={len(segments)}")

        # 3. 分块
        chunks_data = chunk_segments(segments)
        if not chunks_data:
            raise ValueError("文本分块结果为空")
        logger.info(f"[pipeline] doc_id={doc_id} 分块完成，chunks={len(chunks_data)}")

        # 4. 删除旧的分块和向量（reindex 时幂等）
        await db.execute(delete(DocChunk).where(DocChunk.doc_id == doc_id))
        await db.flush()

        # 5. 批量获取 embedding（所有 chunk 一次性提交给 Ollama）
        texts = [c["content"] for c in chunks_data]
        embeddings_list = await get_embeddings_batch(texts)
        logger.info(f"[pipeline] doc_id={doc_id} embedding完成，count={len(embeddings_list)}")

        # 6. 保存 DocChunk + Embedding
        for chunk_data, embedding_vec in zip(chunks_data, embeddings_list):
            chunk = DocChunk(
                doc_id=doc_id,
                chunk_index=chunk_data["chunk_index"],
                content=chunk_data["content"],
                page_no=chunk_data["page_no"],
                heading=chunk_data["heading"],
                token_count=len(chunk_data["content"]),  # 字符数近似 token 数
            )
            db.add(chunk)
            await db.flush()  # 获取 chunk.id

            emb = Embedding(
                chunk_id=chunk.id,
                doc_id=doc_id,
                dept_id=doc.dept_id,
                embedding=embedding_vec,
                model_name=settings.ollama_embed_model,
            )
            db.add(emb)

        # 7. 更新状态
        doc.status = DocStatus.ready
        logger.info(f"[pipeline] doc_id={doc_id} 状态设为 ready，准备提交")
        await db.commit()
        logger.info(f"[pipeline] doc_id={doc_id} 提交成功")


async def _mark_failed(doc_id: int, error_msg: str) -> None:
    """在独立 Session 中将文档标记为失败（防止主 session 回滚影响状态更新）。"""
    try:
        async with async_session_factory() as db:
            doc: Document | None = await db.get(Document, doc_id)
            if doc:
                doc.status = DocStatus.failed
                doc.error_message = error_msg[:500]
                await db.commit()
    except Exception as e:
        logger.error(f"[pipeline] _mark_failed 也失败了: {e}", exc_info=True)
