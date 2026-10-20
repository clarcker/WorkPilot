"""P5：embedding 模型切换（同维度）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import AuditAction, write_audit
from core.config import settings
from core.deps import require_super_admin
from db.models import SystemConfig, User
from db.session import get_db
from schemas.common import BaseResp

router = APIRouter()

ACTIVE_KEY = "active_embedding_model"
REEMBED_TASK_KEY = "embedding_reembed_task"


class ReembedBody(BaseModel):
    target_model: str
    dry_run: bool = False


def _sync_dim(model: str) -> Optional[int]:
    """已知模型维度；未知返回 None。"""
    known = {
        "nomic-embed-text": 768,
        "nomic-embed-text:latest": 768,
        "bge-m3": 1024,
        "mxbai-embed-large": 1024,
    }
    return known.get(model)


@router.get("/embedding/active", response_model=BaseResp[dict])
async def get_active_embedding(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(SystemConfig).where(SystemConfig.key == ACTIVE_KEY))
    active = (row.value or {}).get("model") if row else settings.ollama_embed_model
    task = await db.scalar(select(SystemConfig).where(SystemConfig.key == REEMBED_TASK_KEY))
    return BaseResp.ok({
        "active_model": active,
        "default_model": settings.ollama_embed_model,
        "task": task.value if task else None,
    })


@router.post("/embedding/reembed", response_model=BaseResp[dict])
async def start_reembed(
    body: ReembedBody,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    active_row = await db.scalar(select(SystemConfig).where(SystemConfig.key == ACTIVE_KEY))
    active = (active_row.value or {}).get("model") if active_row else settings.ollama_embed_model
    if body.target_model == active:
        raise HTTPException(400, detail={"code": 40000, "message": "目标模型与当前一致"})
    cur_dim = _sync_dim(active) or 768
    tgt_dim = _sync_dim(body.target_model)
    if tgt_dim is not None and tgt_dim != cur_dim:
        raise HTTPException(
            400,
            detail={"code": 40001, "message": f"异维度切换暂不支持（{cur_dim}→{tgt_dim}）"},
        )

    task_val = {
        "status": "pending" if not body.dry_run else "dry_run",
        "from_model": active,
        "to_model": body.target_model,
        "progress": 0,
        "total": 0,
        "operator": current_user.username,
    }
    from db.models import SystemConfig as SC
    row = await db.scalar(select(SC).where(SC.key == REEMBED_TASK_KEY))
    if row:
        row.value = task_val
        row.updated_by = current_user.id
    else:
        db.add(SC(key=REEMBED_TASK_KEY, value=task_val, updated_by=current_user.id))
    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action="embedding.reembed_start",
        resource_type="embedding",
        resource_id=body.target_model,
        old_value={"model": active},
        new_value=task_val,
    )
    await db.commit()
    if not body.dry_run:
        background_tasks.add_task(_reembed_job, body.target_model, current_user.id)
    return BaseResp.ok(task_val, message="已启动重新向量化" if not body.dry_run else "dry_run 配置")


async def _reembed_job(target_model: str, operator_id: int) -> None:
    """同维度切换：ready 文档分块用目标模型写 embeddings（model_name=目标），完成后切 active。"""
    from services.embedder import get_embedding
    from db.models import DocChunk, DocStatus, Document, Embedding
    from db.session import async_session_factory as sf

    async def _update(val: dict):
        async with sf() as db:
            row = await db.scalar(select(SystemConfig).where(SystemConfig.key == REEMBED_TASK_KEY))
            if row:
                row.value = {**(row.value or {}), **val}
                await db.commit()

    try:
        async with sf() as db:
            docs = (
                await db.execute(select(Document).where(Document.status == DocStatus.ready))
            ).scalars().all()
            doc_ids = [d.id for d in docs]
        total_chunks = 0
        for i, did in enumerate(doc_ids):
            async with sf() as db:
                chunks = (
                    await db.execute(select(DocChunk).where(DocChunk.doc_id == did))
                ).scalars().all()
            for ch in chunks:
                vec = await get_embedding(ch.content, model=target_model)
                async with sf() as db:
                    existing = await db.scalar(
                        select(Embedding).where(
                            Embedding.chunk_id == ch.id,
                            Embedding.model_name == target_model,
                        )
                    )
                    if existing:
                        existing.embedding = vec
                    else:
                        db.add(Embedding(
                            chunk_id=ch.id,
                            doc_id=did,
                            dept_id=0,
                            embedding=vec,
                            model_name=target_model,
                        ))
                    await db.commit()
                total_chunks += 1
            await _update({"progress": i + 1, "total": len(doc_ids), "status": "running",
                           "chunks_done": total_chunks})

        # 原子切换 active
        async with sf() as db:
            row = await db.scalar(select(SystemConfig).where(SystemConfig.key == ACTIVE_KEY))
            if row:
                row.value = {"model": target_model}
                row.updated_by = operator_id
            else:
                db.add(SystemConfig(key=ACTIVE_KEY, value={"model": target_model}, updated_by=operator_id))
            await db.commit()
            await write_audit(
                db,
                operator_id=operator_id,
                operator_name="scheduler",
                action="embedding.reembed_done",
                resource_type="embedding",
                resource_id=target_model,
                new_value={"chunks": total_chunks, "active_model": target_model},
            )
        await _update({"status": "finished", "active_model": target_model, "chunks_done": total_chunks})
    except Exception as exc:
        await _update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
