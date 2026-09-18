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


def rrf_scores_map(
    vec_ids: list[int],
    kw_ids: list[int],
    k: int | None = None,
    w_vec: float | None = None,
    w_kw: float | None = None,
) -> dict[int, float]:
    """RRF 融合分：唯一入口，权重/ k 读配置。"""
    k = k if k is not None else settings.retrieval_rrf_k
    w_vec = w_vec if w_vec is not None else settings.retrieval_w_vec
    w_kw = w_kw if w_kw is not None else settings.retrieval_w_kw
    scores: dict[int, float] = {}
    for w, ranked in ((w_vec, vec_ids), (w_kw, kw_ids)):
        for rank, cid in enumerate(ranked, 1):
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank)
    return scores


def rrf_fuse(
    vec_ids: list[int],
    kw_ids: list[int],
    k: int | None = None,
    w_vec: float | None = None,
    w_kw: float | None = None,
) -> list[int]:
    """返回按 RRF 分降序的 chunk_id 列表。"""
    scores = rrf_scores_map(vec_ids, kw_ids, k, w_vec, w_kw)
    return sorted(scores, key=lambda c: scores[c], reverse=True)


async def _set_hnsw_params(db, cand_k: int) -> None:
    """设置 HNSW 参数；失败用 savepoint 隔离，避免污染整条事务。"""
    try:
        async with db.begin_nested():
            await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(cand_k)}"))
            await db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
    except Exception:
        try:
            async with db.begin_nested():
                await db.execute(text(f"SET LOCAL hnsw.ef_search = {int(cand_k)}"))
        except Exception as exc:
            logger.debug(f"[retriever] hnsw 参数设置失败，使用默认: {exc}")


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
    await _set_hnsw_params(db, cand_k)

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

    # 短块补邻：prev + cur + next，尾部 overlap 去重
    expanded: list[dict] = []
    for m in merged:
        if len(m["content"]) < short_threshold:
            prev_list, next_list = await _fetch_neighbors(
                db, m["doc_id"], m.get("chunk_index") or 0
            )
            parts = []
            for p in prev_list:
                parts.append(_strip_tail_overlap(p, m["content"]))
            parts.append(m["content"])
            for n in next_list:
                parts.append(_strip_tail_overlap(m["content"], n))
            if len(parts) > 1:
                m = {**m, "content": "\n".join(parts)}
        expanded.append(m)

    if settings.retrieval_merge_chunks is False:
        expanded = [
            {**h} for h in hits
        ][: settings.retrieval_top_k]

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
    """相邻块合并；overlap 取前块尾部（与 chunker overlap_chars 对齐）。"""
    base = group[0]
    contents: list[str] = []
    for g in group:
        c = g["content"]
        if contents:
            c = _strip_tail_overlap(contents[-1], c)
        contents.append(c)
    return {
        **base,
        "content": "\n".join(contents),
        "score": max(float(g.get("score") or 0) for g in group),
        "rrf_score": max(float(g.get("rrf_score") or 0) for g in group),
        "must_include": any(bool(g.get("must_include")) for g in group),
        "kw_rank": min((g.get("kw_rank") for g in group if g.get("kw_rank")), default=None),
    }


def _strip_tail_overlap(prev_content: str, cur: str, overlap: int = 80) -> str:
    """去掉 cur 中与 prev 尾部重复的 overlap 前缀。"""
    if prev_content and cur and overlap > 0:
        tail = prev_content[-overlap:]
        if cur.startswith(tail):
            return cur[len(tail):]
    return cur


async def _fetch_neighbors(db, doc_id: int, chunk_index: int) -> tuple[list[str], list[str]]:
    """返回 (prev_contents, next_contents)，各自按 chunk_index 升序。"""
    rows = (
        await db.execute(
            select(DocChunk.chunk_index, DocChunk.content)
            .where(
                DocChunk.doc_id == doc_id,
                DocChunk.chunk_index.in_([chunk_index - 1, chunk_index + 1]),
            )
            .order_by(DocChunk.chunk_index.asc())
        )
    ).all()
    prev = [c for idx, c in rows if idx < chunk_index]
    next_ = [c for idx, c in rows if idx > chunk_index]
    return prev, next_


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
        rrf_map = rrf_scores_map(vec_ids, kw_ids)

        meta: dict[int, dict] = {}
        for r in vec_rows:
            meta[r["chunk_id"]] = {
                **r,
                "vec_score": float(r.get("score") or 0),
                "kw_rank": None,
                "score": float(r.get("score") or 0),
                "rrf_score": rrf_map.get(r["chunk_id"], 0.0),
            }
        for i, r in enumerate(kw_rows):
            cid = r["chunk_id"]
            if cid in meta:
                meta[cid]["kw_rank"] = i + 1
            else:
                meta[cid] = {
                    **r,
                    "vec_score": None,
                    "kw_rank": i + 1,
                    "score": float(r.get("rank") or 0),
                    "rrf_score": rrf_map.get(cid, 0.0),
                    "file_name": r.get("file_name"),
                }

        must_ids: set[int] = set()
        if settings.retrieval_must_include:
            must_ids = set(vec_ids[:3]) | set(kw_ids[:3])
        for m in meta.values():
            m["must_include"] = m["chunk_id"] in must_ids

        ordered = sorted(
            meta.values(),
            key=lambda m: m.get("rrf_score") or 0,
            reverse=True,
        )
        if settings.retrieval_must_include:
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
        f"merged={len(chunks)} must={settings.retrieval_must_include} "
        f"out={[c['chunk_id'] for c in chunks[:5]]}"
    )
    return chunks[:top_k]
