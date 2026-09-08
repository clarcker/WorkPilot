"""
RAG 检索服务：权限过滤的向量相似度搜索。

查询流程：
  1. 从 system_config 加载客服部门 ID 列表（用于 non_customer 权限判断）
  2. 根据用户角色/部门构建文档可见性过滤条件
  3. 用 pgvector <=> 运算符按余弦距离排序，LIMIT top_k

权限规则（与 系统架构.md 一致）：
  global         → 所有用户可见
  non_customer   → 非客服部门用户可见
  dept_only      → 仅本部门用户可见
  specific_users → 在 doc_permissions 白名单的用户可见

super_admin 跳过所有权限过滤，可见所有 ready 文档。
"""
from __future__ import annotations

from typing import TypedDict

from sqlalchemy import select, text

from core.logger import logger
from db.models import SystemConfig
from db.session import async_session_factory


class RetrievedChunk(TypedDict):
    chunk_id: int
    doc_id:   int
    doc_name: str
    content:  str
    heading:  str | None
    page_no:  int | None
    score:    float   # 余弦相似度（0-1），越高越相关


async def retrieve(
    query_embedding: list[float],
    user_id:         int,
    user_dept_id:    int | None,
    user_role:       str,
    top_k:           int = 5,
    min_score:       float = 0.3,   # 低于此阈值的结果视为无关
) -> list[RetrievedChunk]:
    """
    执行权限过滤的向量相似度检索。

    Args:
        query_embedding: 768 维查询向量（已通过 Ollama 生成）
        user_id:         当前用户 ID
        user_dept_id:    当前用户部门 ID（无部门为 None）
        user_role:       'super_admin' | 'dept_admin' | 'employee'
        top_k:           最多返回结果数
        min_score:       最低相似度阈值

    Returns:
        按相似度降序排列的 RetrievedChunk 列表
    """
    async with async_session_factory() as db:
        # 1. 加载客服部门 ID（用于 non_customer 权限判断）
        cs_config = await db.scalar(
            select(SystemConfig.value).where(SystemConfig.key == "customer_service_dept_ids")
        )
        cs_dept_ids: list[int] = cs_config if isinstance(cs_config, list) else []

        # 2. 构建可见性过滤条件
        user_can_see_non_customer = (
            user_dept_id is None or user_dept_id not in cs_dept_ids
        )

        if user_role == "super_admin":
            vis_clause = "TRUE"   # 超级管理员不受权限限制
        else:
            parts = ["(d.visibility = 'global')"]
            if user_can_see_non_customer:
                parts.append("(d.visibility = 'non_customer')")
            if user_dept_id is not None:
                parts.append("(d.visibility = 'dept_only' AND d.dept_id = :user_dept_id)")
            parts.append(
                "(d.visibility = 'specific_users' AND EXISTS ("
                "  SELECT 1 FROM doc_permissions dp"
                "  WHERE dp.doc_id = d.id AND dp.user_id = :user_id"
                "))"
            )
            vis_clause = " OR ".join(parts)

        # 3. 将向量转为 pgvector 字符串格式
        vec_str = "[" + ",".join(f"{x:.8f}" for x in query_embedding) + "]"

        # 4. 执行向量检索
        sql = text(f"""
            SELECT
                dc.id        AS chunk_id,
                dc.doc_id    AS doc_id,
                dc.content   AS content,
                dc.heading   AS heading,
                dc.page_no   AS page_no,
                d.file_name  AS file_name,
                1 - (e.embedding <=> CAST(:query_vec AS vector)) AS score
            FROM embeddings e
            JOIN doc_chunks dc ON dc.id = e.chunk_id
            JOIN documents  d  ON d.id  = e.doc_id
            WHERE d.status = 'ready'
              AND ({vis_clause})
            ORDER BY e.embedding <=> CAST(:query_vec AS vector)
            LIMIT :top_k
        """)

        params: dict = {
            "query_vec":   vec_str,
            "user_id":     user_id,
            "user_dept_id": user_dept_id,
            "top_k":       top_k,
        }

        result = await db.execute(sql, params)
        rows = result.mappings().all()

    chunks = [
        RetrievedChunk(
            chunk_id=int(row["chunk_id"]),
            doc_id=int(row["doc_id"]),
            doc_name=str(row["file_name"]),
            content=str(row["content"]),
            heading=row["heading"],
            page_no=row["page_no"],
            score=float(row["score"]),
        )
        for row in rows
        if float(row["score"]) >= min_score
    ]

    logger.debug(f"[retriever] user={user_id} 检索到 {len(chunks)}/{len(rows)} 个相关 chunk")
    return chunks
