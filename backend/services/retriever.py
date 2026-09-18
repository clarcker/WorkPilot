"""
RAG 检索：向量 + 关键词混合，RRF 融合，分块合并（R3+R4）。

流程：
  1. 权限过滤（SQL 内完成）
  2. 向量候选扩展 → 阈值
  3. 关键词 ts_rank 并行检索（jieba 预分词）
  4. RRF 融合 → TopK
  5. 相邻块合并 / 短块补邻
"""
from __future__ import annotations

from typing import TypedDict

from sqlalchemy import select, text

from core.config import settings
from core.logger import logger
from db.models import DocChunk, SystemConfig
from db.session import async_session_factory
from services.fts import build_tsquery


class RetrievedChunk(TypedDict):
    chunk_id: int
    doc_id:   int
    doc_name: str
    content:  str
    heading:  str | None
    page_no:  int | None
    chunk_index: int
    score:    float
    vec_score: float | None
    kw_rank:  int | None


def _candidate_k(top_k: int) -> int:
    return max(50, min(top_k * 20, 200))


def rrf_fuse(
    vec_ids: list[int],
    kw_ids: list[int],
    k: int = 60,
    w_vec: float = 0.7,
    w_kw: float = 0.3,
) -> list[int]:
    """RRF：只消费排名。"""
    scores: dict[int, float] = {}
    for w, ranked in ((w_vec, vec_ids), (w_kw, kw_ids)):
        for rank, cid in enumerate(ranked, 1):
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank)
    return sorted(scores, key=lambda c: scores[c], reverse=True)


def _build_vis_clause(
    user_role: str,
    user_dept_id: int | None,
    user_id: int,
    cs_dept_ids: list[int],
) -> str:
    if user_role == "super_admin":
        return "TRUE"
    user_can_see_nc = user_dept_id is None or user_dept_id not in cs_dept_ids
    parts = ["(d.visibility = 'global')"]
    if user_can_see_nc:
        parts.append("(d.visibility = 'non_customer')")
    if user_dept_id is not None:
        parts.append("(d.visibility = 'dept_only' AND d.dept_id = :user_dept_id)")
    parts.append(
        "(d.visibility = 'specific_users' AND EXISTS ("
        "  SELECT 1 FROM doc_permissions dp"
        "  WHERE dp.doc_id = d.id AND dp.user_id = :user_id"
        "))"
    )
    return " OR ".join(parts)


async def _vector_search(
    db,
    vec_str: str,
    vis_clause: str,
    user_id: int,
    user_dept_id: int | None,
    cand_k: int,
    min_score: float,
) -> list[dict]:
    try:
        await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(cand_k)}"))
        await db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    except Exception:
        try:
            await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(cand_k)}"))
        except Exception:
            pass

    sql = text(f"""
        SELECT
            dc.id AS chunk_id, dc.doc_id, dc.content, dc.heading,
            dc.page_no, dc.chunk_index, d.file_name,
            1 - (e.embedding <=> CAST(:query_vec AS vector)) AS score
        FROM embeddings e
        JOIN doc_chunks dc ON dc.id = e.chunk_id
        JOIN documents  d  ON d.id  = e.doc_id
        WHERE d.status = 'ready' AND ({vis_clause})
        ORDER BY e.embedding <=> CAST(:query_vec AS vector)
        LIMIT :candidate_k
    """)
    rows = (
        await db.execute(sql, {
            "query_vec": vec_str,
            "user_id": user_id,
            "user_dept_id": user_dept_id,
            "candidate_k": cand_k,
        })
    ).mappings().all()
    return [dict(r) for r in rows if float(r["score"]) >= min_score]


async def _keyword_search(
    db,
    query_text: str,
    vis_clause: str,
    user_id: int,
    user_dept_id: int | None,
    cand_k: int,
) -> list[dict]:
    """关键词检索。无 tsvector 列或 jieba 异常时返回空列表。"""
    tsq = build_tsquery(query_text)
    if not tsq:
        return []
    try:
        sql = text(f"""
            SELECT
                dc.id AS chunk_id, dc.doc_id, dc.content, dc.heading,
                dc.page_no, dc.chunk_index, d.file_name,
                ts_rank_cd(dc.content_tsv, to_tsquery('simple', :tsq)) AS rank
            FROM doc_chunks dc
            JOIN documents d ON d.id = dc.doc_id
            WHERE d.status = 'ready'
              AND ({vis_clause})
              AND dc.content_tsv @@ to_tsquery('simple', :tsq)
            ORDER BY rank DESC
            LIMIT :candidate_k
        """)
        rows = (
            await db.execute(sql, {
                "tsq": tsq,
                "user_id": user_id,
                "user_dept_id": user_dept_id,
                "candidate_k": cand_k,
            })
        ).mappings().all()
        return [dict(r) for r in rows]
    except Exception as exc:
        # content_tsv 列可能尚未回填
        logger.debug(f"[retriever] 关键词检索降级: {exc}")
        return []


async def _merge_chunks(
    db,
    hits: list[dict],
    budget: int = 4000,
    short_threshold: int = 200,
) -> list[RetrievedChunk]:
    """R4：去重 → 相邻合并 → 短块补邻 → 预算截断。"""
    if not hits:
        return []

    # 按 (doc_id, chunk_index) 去重，保留首次出现（RRF 已排序）
    seen: set[int] = set()
    unique: list[dict] = []
    for h in hits:
        cid = h["chunk_id"]
        if cid in seen:
            continue
        seen.add(cid)
        unique.append(h)

    # 同文档相邻块合并
    by_doc: dict[int, list[dict]] = {}
    for h in unique:
        by_doc.setdefault(h["doc_id"], []).append(h)

    merged: list[dict] = []
    for doc_id, items in by_doc.items():
        items = sorted(items, key=lambda x: x.get("chunk_index") or 0)
        group = [items[0]]
        for prev, cur in zip(items, items[1:]):
            pi, ci = prev.get("chunk_index") or 0, cur.get("chunk_index") or 0
            if ci == pi + 1:
                group.append(cur)
            else:
                merged.append(_flatten_group(group))
                group = [cur]
        merged.append(_flatten_group(group))

    # 短块补邻
    expanded: list[dict] = []
    for m in merged:
        if len(m["content"]) < short_threshold:
            neighbors = await _fetch_neighbors(db, m["doc_id"], m["chunk_index"])
            if neighbors:
                m = {**m, "content": "\n".join(neighbors + [m["content"]])}
        expanded.append(m)

    # must_include 优先，再按融合分
    expanded.sort(
        key=lambda x: (
            0 if x.get("must_include") else 1,
            -(x.get("rrf_score") or x.get("score") or 0),
        ),
    )
    total = 0
    result: list[RetrievedChunk] = []
    for m in expanded:
        clen = len(m["content"])
        must = bool(m.get("must_include"))
        if total + clen > budget and result and not must:
            if clen > 400:
                continue
        total += clen
        result.append(RetrievedChunk(
            chunk_id=m["chunk_id"],
            doc_id=m["doc_id"],
            doc_name=m.get("file_name") or m.get("doc_name") or "",
            content=m["content"],
            heading=m.get("heading"),
            page_no=m.get("page_no"),
            chunk_index=m.get("chunk_index") or 0,
            score=float(m.get("score") or 0),
            vec_score=m.get("vec_score"),
            kw_rank=m.get("kw_rank"),
        ))
        if len(result) >= 12:
            break
    return result


def _flatten_group(group: list[dict]) -> dict:
    """相邻块合并为一条；must_include 任一组员为真则保留。"""
    base = group[0]
    contents = []
    seen_prefix = ""
    for g in group:
        c = g["content"]
        if seen_prefix and c.startswith(seen_prefix[:40]):
            c = c[len(seen_prefix[:40]):]
        elif contents and contents[-1].endswith(c[:40]):
            c = c[40:]
        contents.append(c)
        seen_prefix = c
    return {
        **base,
        "content": "\n".join(contents),
        "score": max(float(g.get("score") or 0) for g in group),
        "rrf_score": max(float(g.get("rrf_score") or 0) for g in group),
        "must_include": any(bool(g.get("must_include")) for g in group),
        "kw_rank": min((g.get("kw_rank") for g in group if g.get("kw_rank")), default=None),
    }


async def _fetch_neighbors(db, doc_id: int, chunk_index: int) -> list[str]:
    rows = (
        await db.execute(
            select(DocChunk.content)
            .where(
                DocChunk.doc_id == doc_id,
                DocChunk.chunk_index.in_([chunk_index - 1, chunk_index + 1]),
            )
        )
    ).scalars().all()
    return list(rows)


async def retrieve(
    query_embedding: list[float],
    user_id: int,
    user_dept_id: int | None,
    user_role: str,
    query_text: str = "",
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    """混合检索入口。query_text 为空时退化为纯向量。"""
    top_k = top_k if top_k is not None else settings.retrieval_top_k
    min_score = min_score if min_score is not None else settings.retrieval_min_score
    cand_k = _candidate_k(top_k)
    vec_str = "[" + ",".join(f"{x:.8f}" for x in query_embedding) + "]"

    async with async_session_factory() as db:
        cs_config = await db.scalar(
            select(SystemConfig.value).where(SystemConfig.key == "customer_service_dept_ids")
        )
        cs_dept_ids: list[int] = cs_config if isinstance(cs_config, list) else []
        vis_clause = _build_vis_clause(user_role, user_dept_id, user_id, cs_dept_ids)

        vec_rows = await _vector_search(
            db, vec_str, vis_clause, user_id, user_dept_id, cand_k, min_score
        )
        kw_rows: list[dict] = []
        if query_text and settings.retrieval_enable_fts:
            kw_rows = await _keyword_search(
                db, query_text, vis_clause, user_id, user_dept_id, cand_k
            )

        vec_ids = [r["chunk_id"] for r in vec_rows]
        kw_ids = [r["chunk_id"] for r in kw_rows]

        # 构建 chunk_id → meta；score 用于展示，rrf_score 用于排序
        meta: dict[int, dict] = {}
        rrf_scores: dict[int, float] = {}
        for w, ranked in ((0.65, vec_ids), (0.35, kw_ids)):
            for rank, cid in enumerate(ranked, 1):
                rrf_scores[cid] = rrf_scores.get(cid, 0.0) + w / (60 + rank)

        for r in vec_rows:
            meta[r["chunk_id"]] = {
                **r,
                "vec_score": float(r.get("score") or 0),
                "kw_rank": None,
                "score": float(r.get("score") or 0),
                "rrf_score": rrf_scores.get(r["chunk_id"], 0.0),
            }
        for i, r in enumerate(kw_rows):
            cid = r["chunk_id"]
            if cid in meta:
                meta[cid]["kw_rank"] = i + 1
            else:
                # 纯关键词命中：score 用 ts_rank（仅排序展示），rrf_score 单独保留
                meta[cid] = {
                    **r,
                    "vec_score": None,
                    "kw_rank": i + 1,
                    "score": float(r.get("rank") or 0),
                    "rrf_score": rrf_scores.get(cid, 0.0),
                    "file_name": r.get("file_name"),
                }

        # 保证两路 Top3 一定进入合并候选，避免专有词命中被 RRF 压掉
        must_ids = set(vec_ids[:3]) | set(kw_ids[:3])
        for m in meta.values():
            m["must_include"] = m["chunk_id"] in must_ids
        ordered = sorted(
            meta.values(),
            key=lambda m: (
                0 if m.get("must_include") else 1,
                -(m.get("rrf_score") or 0),
            ),
        )

        chunks = await _merge_chunks(db, ordered[: max(top_k * 4, 20)])

    logger.debug(
        f"[retriever] user={user_id} vec={len(vec_rows)} kw={len(kw_rows)} "
        f"merged={len(chunks)} must={sorted(must_ids)} "
        f"kw_ids={kw_ids[:5]} out={[c['chunk_id'] for c in chunks]}"
    )
    return chunks[:top_k]
