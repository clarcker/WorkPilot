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
    lifecycle: str | None
    effective_date: str | None
    superseded_by_name: str | None
    lifecycle_note: str | None


def build_lifecycle_clause(user_role: str, time_scope: str = "current") -> str:
    """
    Q1：按角色 + 时间范围过滤 documents.lifecycle。

    - current（默认）：员工仅 effective；管理员 effective + draft
    - historical：effective + superseded；管理员额外 draft
    draft 对员工不召回且不透露存在（与权限过滤同一原则）。
    """
    is_admin = user_role in ("super_admin", "dept_admin")
    historical = (time_scope or "current") == "historical"
    if historical:
        if is_admin:
            return "d.lifecycle IN ('effective', 'superseded', 'draft')"
        return "d.lifecycle IN ('effective', 'superseded')"
    if is_admin:
        return "d.lifecycle IN ('effective', 'draft')"
    return "d.lifecycle = 'effective'"


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
    lifecycle_clause: str,
    user_id: int,
    user_dept_id: int | None,
    cand_k: int,
    min_score: float,
) -> list[dict]:
    """候选扩展 → 阈值 → 与 top_k 解耦的 SQL 过滤（R2 + Q1 lifecycle）。"""
    await _set_hnsw_params(db, cand_k)

    sql = text(f"""
        SELECT * FROM (
            SELECT
                dc.id AS chunk_id, dc.doc_id, dc.content, dc.heading,
                dc.page_no, dc.chunk_index, d.file_name,
                d.lifecycle, d.effective_date,
                newer.file_name AS superseded_by_name,
                1 - (e.embedding <=> CAST(:query_vec AS vector)) AS score
            FROM embeddings e
            JOIN doc_chunks dc ON dc.id = e.chunk_id
            JOIN documents  d  ON d.id  = e.doc_id
            LEFT JOIN documents newer
              ON newer.supersedes_doc_id = d.id
             AND newer.lifecycle = 'effective'
            WHERE d.status = 'ready'
              AND ({vis_clause})
              AND ({lifecycle_clause})
            ORDER BY e.embedding <=> CAST(:query_vec AS vector)
            LIMIT :candidate_k
        ) candidates
        WHERE score >= :min_score
        ORDER BY score DESC
    """)
    rows = (
        await db.execute(sql, {
            "query_vec": vec_str,
            "user_id": user_id,
            "user_dept_id": user_dept_id,
            "candidate_k": cand_k,
            "min_score": min_score,
        })
    ).mappings().all()
    return [dict(r) for r in rows]


async def _keyword_search(
    db,
    query_text: str,
    vis_clause: str,
    lifecycle_clause: str,
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
                d.lifecycle, d.effective_date,
                newer.file_name AS superseded_by_name,
                ts_rank_cd(dc.content_tsv, to_tsquery('simple', :tsq)) AS rank
            FROM doc_chunks dc
            JOIN documents d ON d.id = dc.doc_id
            LEFT JOIN documents newer
              ON newer.supersedes_doc_id = d.id
             AND newer.lifecycle = 'effective'
            WHERE d.status = 'ready'
              AND ({vis_clause})
              AND ({lifecycle_clause})
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

    # pinned（配额换入）优先，再按融合分；不再使用 must_include
    expanded.sort(
        key=lambda x: (
            0 if x.get("pinned") else 1,
            -(x.get("rrf_score") or x.get("score") or 0),
        ),
    )
    total = 0
    result: list[RetrievedChunk] = []
    for m in expanded:
        clen = len(m["content"])
        pinned = bool(m.get("pinned"))
        if total + clen > budget and result and not pinned:
            if clen > 400:
                continue
        total += clen
        lifecycle = m.get("lifecycle") or "effective"
        superseded_by = m.get("superseded_by_name")
        note = None
        if lifecycle == "superseded":
            if superseded_by:
                note = f"已被 {superseded_by} 替代（历史版本）"
            else:
                note = "历史版本，可能已有现行制度"
        elif lifecycle == "draft":
            note = "草案 / 征求意见稿，尚未正式生效"
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
            lifecycle=lifecycle,
            effective_date=(
                m.get("effective_date").isoformat()
                if hasattr(m.get("effective_date"), "isoformat")
                else m.get("effective_date")
            ),
            superseded_by_name=superseded_by,
            lifecycle_note=note,
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
        "pinned": any(bool(g.get("pinned")) for g in group),
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


async def _expand_parent_sections(
    db,
    hits: list[dict],
    budget: int | None = None,
) -> list[dict]:
    """
    小块检索、大块生成：把命中 chunk 替换为同 (doc_id, heading) 的整节内容。
    无 heading 的 chunk 保持原样。整节超 budget 时保留原 chunk。
    """
    if not settings.retrieval_parent_expand:
        return hits
    budget = budget if budget is not None else settings.retrieval_parent_budget
    if not hits:
        return hits

    section_keys = []
    seen = set()
    for h in hits:
        heading = h.get("heading")
        doc_id = h.get("doc_id")
        if not heading or doc_id is None:
            continue
        key = (doc_id, heading)
        if key not in seen:
            seen.add(key)
            section_keys.append(key)
    if not section_keys:
        return hits

    section_map: dict[tuple[int, str], list[dict]] = {k: [] for k in section_keys}
    # 按 heading 批量取同节 chunk
    for doc_id, heading in section_keys:
        rows = (
            await db.execute(
                select(DocChunk.chunk_index, DocChunk.content, DocChunk.heading, DocChunk.page_no)
                .where(DocChunk.doc_id == doc_id, DocChunk.heading == heading)
                .order_by(DocChunk.chunk_index.asc())
            )
        ).all()
        section_map[(doc_id, heading)] = [
            {"chunk_index": r[0], "content": r[1], "heading": r[2], "page_no": r[3]}
            for r in rows
        ]

    expanded: list[dict] = []
    used_sections: set[tuple[int, str]] = set()
    for h in hits:
        heading = h.get("heading")
        key = (h.get("doc_id"), heading)
        if heading and key in section_map and key not in used_sections:
            section_rows = section_map[key]
            section_text = "\n".join(r["content"] for r in section_rows).strip()
            if section_text and len(section_text) <= budget:
                used_sections.add(key)
                expanded.append({
                    **h,
                    "content": section_text,
                    "chunk_index": section_rows[0]["chunk_index"],
                    "parent_expanded": True,
                    "section_chunk_count": len(section_rows),
                })
                continue
        expanded.append(h)
    return expanded


async def retrieve(
    query_embedding: list[float],
    user_id: int,
    user_dept_id: int | None,
    user_role: str,
    query_text: str = "",
    top_k: int | None = None,
    min_score: float | None = None,
    time_scope: str = "current",
) -> list[RetrievedChunk]:
    """混合检索入口。query_text 为空时退化为纯向量。"""
    from core.config import maybe_reload_settings
    maybe_reload_settings()
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
        lifecycle_clause = build_lifecycle_clause(user_role, time_scope)

        vec_rows = await _vector_search(
            db, vec_str, vis_clause, lifecycle_clause,
            user_id, user_dept_id, cand_k, min_score,
        )
        kw_rows: list[dict] = []
        if query_text and settings.retrieval_enable_fts:
            kw_rows = await _keyword_search(
                db, query_text, vis_clause, lifecycle_clause,
                user_id, user_dept_id, cand_k,
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

        # E5：关键词配额——换入项标 pinned，合并阶段按 (not pinned, -rrf) 排序，
        # 避免二次 sort 把低分 kw 项挤回末尾（否则配额是空操作）。
        kw_quota = 2 if settings.retrieval_must_include else 0
        ordered = sorted(
            meta.values(),
            key=lambda m: m.get("rrf_score") or 0,
            reverse=True,
        )
        if kw_quota > 0 and kw_ids:
            orig_ids = {m["chunk_id"] for m in ordered[:top_k]}
            top = list(ordered[:top_k])
            top_kw = [m for m in top if m.get("kw_rank") is not None]
            if len(top_kw) < kw_quota:
                rest_kw = [
                    m for m in ordered[top_k:]
                    if m.get("kw_rank") is not None
                ][: kw_quota - len(top_kw)]
                non_kw_tail = [i for i, m in enumerate(top) if m.get("kw_rank") is None]
                for m in rest_kw:
                    if not non_kw_tail:
                        break
                    top[non_kw_tail.pop()] = m
                for m in top:
                    m["pinned"] = m["chunk_id"] not in orig_ids
                kept = {m["chunk_id"] for m in top}
                ordered = top + [m for m in ordered[top_k:] if m["chunk_id"] not in kept]
            else:
                for m in top:
                    m["pinned"] = False

        chunks = await _merge_chunks(db, ordered[: max(top_k * 4, 20)])
        # 父块扩展：在 merge 之后、返回之前，用整节替换命中小块
        meta_by_cid = {m.get("chunk_id"): m for m in ordered}
        hit_dicts = []
        for c in chunks:
            d = dict(c)
            src = meta_by_cid.get(c.get("chunk_id")) or {}
            d.setdefault("heading", c.get("heading"))
            d.setdefault("doc_id", c.get("doc_id"))
            d["rrf_score"] = src.get("rrf_score") or c.get("score")
            hit_dicts.append(d)
        # 用 ordered 的 meta 信息补全 lifecycle 等
        for d in hit_dicts:
            src = meta_by_cid.get(d.get("chunk_id")) or {}
            for k in ("lifecycle", "effective_date", "superseded_by_name", "file_name"):
                if k in src and src[k] is not None:
                    d.setdefault(k, src[k])
        expanded_hits = await _expand_parent_sections(db, hit_dicts)
        # 重新压回 RetrievedChunk（保留 merge 后的 score 等）
        chunk_by_id = {c["chunk_id"]: c for c in chunks}
        final_chunks: list[RetrievedChunk] = []
        for h in expanded_hits:
            base = chunk_by_id.get(h.get("chunk_id")) or h
            lifecycle = h.get("lifecycle") or base.get("lifecycle") or "effective"
            superseded_by = h.get("superseded_by_name") or base.get("superseded_by_name")
            note = None
            if lifecycle == "superseded":
                note = (
                    f"已被 {superseded_by} 替代（历史版本）"
                    if superseded_by else "历史版本，可能已有现行制度"
                )
            elif lifecycle == "draft":
                note = "草案 / 征求意见稿，尚未正式生效"
            eff = h.get("effective_date") or base.get("effective_date")
            if hasattr(eff, "isoformat"):
                eff = eff.isoformat()
            final_chunks.append(RetrievedChunk(
                chunk_id=base.get("chunk_id") or h.get("chunk_id"),
                doc_id=h.get("doc_id") or base.get("doc_id"),
                doc_name=h.get("file_name") or base.get("doc_name") or "",
                content=h.get("content") or base.get("content") or "",
                heading=h.get("heading") or base.get("heading"),
                page_no=h.get("page_no") or base.get("page_no"),
                chunk_index=h.get("chunk_index") if h.get("chunk_index") is not None else base.get("chunk_index") or 0,
                score=float(base.get("score") or 0),
                vec_score=base.get("vec_score"),
                kw_rank=base.get("kw_rank"),
                lifecycle=lifecycle,
                effective_date=eff,
                superseded_by_name=superseded_by,
                lifecycle_note=note,
            ))
            if len(final_chunks) >= 12:
                break
        chunks = final_chunks

    logger.debug(
        f"[retriever] user={user_id} scope={time_scope} vec={len(vec_rows)} kw={len(kw_rows)} "
        f"merged={len(chunks)} kw_quota={kw_quota} "
        f"out={[c['chunk_id'] for c in chunks[:5]]}"
    )
    return chunks[:top_k]
