"""
Eval runner — 运行 golden cases 评测 RAG 工作流。

指标（E2 重定义）：
- doc_hit@3 / doc_hit_rate: 期望文档出现在 sources 前 3（仅 expected_doc_title 非空）
- recall@1: 期望文档是 sources 第 1
- mrr: 1/排名，未命中 0，对 expected_doc_title case 平均
- heading_hit: 期望 heading 出现在命中 chunk 的 heading
- tool_call_accuracy / intent_accuracy / permission_pass_rate: 保留
- citation_rate: 仅 should_cite 且 doc_hit@3 的 case
- skip_generation=True 时 citation_rate 不评估答案正文质量，只看 sources 列表

conversation_history: case 可带 history 字段（list of {role,content}），用于多轮改写评测。
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.logger import logger
from graph.state import RAGState
from graph.workflow import rag_graph
from services.embedder import get_embedding
from services.llm_client import chat_complete

_CASES_PATH = Path(__file__).parent / "cases.json"
DEFAULT_CASE_TIMEOUT = 90.0


@dataclass
class CaseResult:
    case_id: str
    question: str
    expected_intent: str
    actual_intent: str
    intent_correct: bool
    doc_hit: bool          # Top-3 命中（保留字段名兼容旧报告）
    doc_rank: int          # 期望文档在 sources 中的排名，1-based；未命中 -1
    recall_at_1: bool
    heading_hit: bool
    mrr: float             # 本条 1/rank 或 0
    tool_call_correct: bool
    has_citation: bool
    forbidden_doc_leaked: bool
    latency_ms: int
    group: str = ""
    timed_out: bool = False
    error: Optional[str] = None
    detail: str = ""


@dataclass
class EvalReport:
    total_cases: int
    scored_cases: int
    timeout_count: int
    intent_accuracy: float
    doc_hit_rate: float
    recall_at_1: float
    mrr: float
    heading_hit_rate: float
    tool_call_accuracy: float
    citation_rate: float
    permission_pass_rate: float
    avg_latency_ms: int
    case_results: list[CaseResult] = field(default_factory=list)
    failed_cases: list[dict] = field(default_factory=list)
    timeout_cases: list[dict] = field(default_factory=list)
    by_group: dict = field(default_factory=dict)


async def warmup() -> float:
    """
    预热 Ollama，返回耗时（秒）。

    Ollama 会在空闲若干分钟后把模型换出内存，下次调用要重新加载
    （这台开发机上 qwen2.5:7b 约 45~55s）。不预热的话第一条 case 会
    白白背上这个开销：既可能直接判超时，也会把 avg_latency_ms 拉偏。
    预热不计入任何指标。
    """
    start = time.time()
    try:
        await asyncio.gather(
            chat_complete([{"role": "user", "content": "hi"}], temperature=0, max_tokens=1),
            get_embedding("warmup"),
        )
    except Exception as exc:
        # 预热失败不阻断评测——真实的失败会在各条 case 里如实反映出来
        logger.warning(f"[eval] 预热失败（继续评测）: {type(exc).__name__}: {exc}")
    elapsed = time.time() - start
    logger.info(f"[eval] 模型预热完成，耗时 {elapsed:.1f}s")
    return elapsed


def load_cases() -> list[dict]:
    with open(_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _args_match(expected: dict, actual: dict) -> tuple[bool, str]:
    """
    子集匹配：expected 中声明的每个键都要在 actual 中出现且值相等。
    actual 里的额外参数不算错（模型可以多带可选参数）。
    """
    if not expected:
        return True, ""
    actual = actual or {}
    bad = []
    for k, v in expected.items():
        if k not in actual:
            bad.append(f"缺少参数 {k}")
        elif str(actual[k]).strip() != str(v).strip():
            bad.append(f"参数 {k}: 期望={v}, 实际={actual[k]}")
    return (not bad), "; ".join(bad)


async def run_case(
    case: dict,
    user_id: int = 1,
    user_role: str = "employee",
    user_dept_id: int | None = 1,
    skip_generation: bool = True,
    tool_dry_run: bool = True,
    gen_max_tokens: int | None = 512,
    timeout: float = DEFAULT_CASE_TIMEOUT,
) -> CaseResult:
    # 部分 case 必须以固定身份运行（例如权限负例），as_user 覆盖调用者身份
    as_user = case.get("as_user") or {}
    run_user_id = as_user.get("user_id", user_id)
    run_user_role = as_user.get("user_role", user_role)
    run_user_dept_id = as_user.get("user_dept_id", user_dept_id)

    start = time.time()
    # ── 多轮 history ────────────────────────────────────────────
    history = case.get("conversation_history") or case.get("history") or []

    initial_state = RAGState(
        query=case["question"],
        user_id=run_user_id,
        user_role=run_user_role,
        user_dept_id=run_user_dept_id,
        conversation_history=history,
        anonymized_query="",
        intent="",
        retrieved_chunks=[],
        full_answer="",
        sources=[],
        error=None,
        token_queue=None,
        need_tool=False,
        tool_name=None,
        tool_args={},
        tool_result=None,
        permission_denied=None,
        trace=[],
        tool_success=None,
        tool_error=None,
        tool_step=0,
        tool_history=[],
        max_tool_steps=4,
        node_steps=[],
        requires_confirmation=False,
        confirm_payload=None,
        missing_slots=None,
        rewritten_query=None,
        skip_generation=skip_generation,
        gen_max_tokens=gen_max_tokens,
        tool_dry_run=tool_dry_run,
    )

    def _blank(timed_out: bool, err: str) -> CaseResult:
        return CaseResult(
            case_id=case["id"], question=case["question"],
            expected_intent=case.get("expected_intent", ""), actual_intent="",
            intent_correct=False, doc_hit=False, doc_rank=-1,
            recall_at_1=False, heading_hit=False, mrr=0.0,
            tool_call_correct=False,
            has_citation=False, forbidden_doc_leaked=False,
            latency_ms=int((time.time() - start) * 1000),
            group=case.get("group") or "",
            timed_out=timed_out, error=err,
            detail=f"超时（>{timeout:.0f}s），本条无观测值" if timed_out else err,
        )

    try:
        final_state = await asyncio.wait_for(rag_graph.ainvoke(initial_state), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        # str(TimeoutError()) 是空字符串，必须自己写原因，否则报告里只剩一个空 detail
        logger.warning(f"[eval] {case['id']} 超时 >{timeout}s: {case['question']!r}")
        return _blank(timed_out=True, err=f"TimeoutError: 超过 {timeout:.0f}s")
    except Exception as exc:
        logger.error(f"[eval] {case['id']} 执行异常: {exc!r}", exc_info=True)
        return _blank(timed_out=False, err=f"{type(exc).__name__}: {exc}")

    latency_ms = int((time.time() - start) * 1000)
    actual_intent = final_state.get("intent", "")
    expected_intent = case.get("expected_intent", "")
    intent_correct = actual_intent == expected_intent

    # ── 检索指标（E2）───────────────────────────────────────────
    sources = final_state.get("sources", [])
    source_doc_names = [s.get("doc_name", "") for s in sources]

    expected_title = (case.get("expected_doc_title") or "").strip()
    expected_heading = (case.get("expected_heading") or "").strip()
    doc_rank = -1
    doc_hit = True          # 无期望文档时不计入分母，这里先标 True
    recall_at_1 = True
    heading_hit = True
    mrr = 1.0
    if expected_title:
        # 优先精确文件名匹配，其次子串（兼容旧 case）
        for i, name in enumerate(source_doc_names, 1):
            if name == expected_title or expected_title in name or (
                expected_title.endswith(".md") and name.startswith(expected_title)
            ):
                doc_rank = i
                break
        doc_hit = 0 < doc_rank <= 3
        recall_at_1 = doc_rank == 1
        mrr = 1.0 / doc_rank if doc_rank > 0 else 0.0
        if expected_heading:
            hit_chunk = None
            if doc_rank > 0:
                hit_chunk = sources[doc_rank - 1] if doc_rank <= len(sources) else None
            if hit_chunk:
                h = (hit_chunk.get("heading") or "")
                heading_hit = expected_heading in h
            else:
                heading_hit = False
        else:
            heading_hit = doc_hit  # 未标注 heading 时与 doc_hit 同

    # 引用：仅 should_cite 且 doc_hit@3 时才算有效引用
    if case.get("should_cite"):
        has_citation = bool(sources) and doc_hit
    else:
        has_citation = True

    # 工具调用
    expected_tool = case.get("expected_tool")
    tool_history = final_state.get("tool_history") or []
    actual_tool = final_state.get("tool_name")
    actual_args = final_state.get("tool_args") or {}
    tool_success = final_state.get("tool_success")
    tool_error = final_state.get("tool_error")

    hist_names = [h.get("name") for h in tool_history]
    hist_hit = None
    if expected_tool:
        for h in tool_history:
            if h.get("name") == expected_tool:
                hist_hit = h
                break

    tool_detail = ""
    if expected_tool:
        if actual_tool != expected_tool and hist_hit is None:
            tool_call_correct = False
            tool_detail = f"工具: 期望={expected_tool}, 实际={actual_tool or hist_names or '无'}"
        else:
            check_args = (hist_hit or {}).get("args") or actual_args
            check_ok = (hist_hit or {}).get("success")
            if check_ok is None:
                check_ok = tool_success
            args_ok, args_msg = _args_match(case.get("expected_tool_args", {}), check_args)
            exec_ok = (not case.get("expect_tool_success")) or check_ok is True
            if case.get("expect_tool_denied"):
                exec_ok = check_ok is False and bool(
                    (hist_hit or {}).get("error") or tool_error or final_state.get("permission_denied")
                )
            tool_call_correct = args_ok and exec_ok
            if not args_ok:
                tool_detail = f"工具参数不符（实际={check_args}）: {args_msg}"
            elif not exec_ok:
                tool_detail = f"工具 {expected_tool} 执行结果不符: {tool_error or (hist_hit or {}).get('error')}"
    else:
        tool_call_correct = actual_tool is None and not hist_names
        if not tool_call_correct:
            tool_detail = f"工具: 期望不调用, 实际={actual_tool or hist_names}({actual_args})"

    # 权限负例
    forbidden_doc_leaked = False
    forbidden_title = case.get("forbidden_doc_title")
    if forbidden_title:
        forbidden_doc_leaked = any(forbidden_title in name for name in source_doc_names)

    detail_parts = []
    if not intent_correct:
        detail_parts.append(f"意图: 期望={expected_intent}, 实际={actual_intent}")
    if expected_title and not doc_hit:
        detail_parts.append(
            f"doc_hit@3 miss: 期望={expected_title} rank={doc_rank} "
            f"召回={source_doc_names or '无'}"
        )
    if tool_detail:
        detail_parts.append(tool_detail)
    if case.get("should_cite") and not has_citation:
        detail_parts.append("citation 无效（未命中期望文档或 sources 空）")
    if forbidden_doc_leaked:
        detail_parts.append(f"泄露受限文档: {forbidden_title}")

    return CaseResult(
        case_id=case["id"], question=case["question"],
        expected_intent=expected_intent, actual_intent=actual_intent,
        intent_correct=intent_correct, doc_hit=doc_hit,
        doc_rank=doc_rank, recall_at_1=recall_at_1,
        heading_hit=heading_hit, mrr=mrr,
        tool_call_correct=tool_call_correct, has_citation=has_citation,
        forbidden_doc_leaked=forbidden_doc_leaked,
        latency_ms=latency_ms,
        group=case.get("group") or "",
        error=final_state.get("error"),
        detail="; ".join(detail_parts),
    )


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


async def run_eval(
    user_id: int = 1,
    user_role: str = "employee",
    user_dept_id: int | None = 1,
    skip_generation: bool = True,
    tool_dry_run: bool = True,
    concurrency: int = 1,
    timeout: float = DEFAULT_CASE_TIMEOUT,
) -> EvalReport:
    """
    Args:
        skip_generation: 跳过答案生成节点（指标不依赖答案正文，默认开启以避免超时）
        tool_dry_run:    工具演练模式，校验参数但不写库
        concurrency:     并发条数。>1 时 avg_latency_ms 会受相互争抢影响，
                         想看真实单条延迟请保持 1。
        timeout:         单条 case 墙钟上限
    """
    cases = load_cases()
    if not cases:
        return EvalReport(total_cases=0, scored_cases=0, timeout_count=0,
                          intent_accuracy=0, doc_hit_rate=0, tool_call_accuracy=0,
                          citation_rate=0, permission_pass_rate=0, avg_latency_ms=0)

    # 先把两个模型加载进内存，避免第一条 case 独自承担冷启动开销
    await warmup()

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _run(case: dict) -> CaseResult:
        async with sem:
            return await run_case(
                case, user_id, user_role, user_dept_id,
                skip_generation=skip_generation, tool_dry_run=tool_dry_run,
                timeout=timeout,
            )

    # gather 保序，下面按下标与 cases 对齐
    results: list[CaseResult] = list(await asyncio.gather(*(_run(c) for c in cases)))

    total = len(results)
    pairs = list(zip(results, cases))

    scored = [(r, c) for r, c in pairs if not r.timed_out]
    timeouts = [r for r in results if r.timed_out]

    doc_pairs = [(r, c) for r, c in scored if (c.get("expected_doc_title") or "").strip()]
    cite_pairs = [(r, c) for r, c in scored if c.get("should_cite") and r.doc_hit]
    perm_pairs = [(r, c) for r, c in scored if c.get("forbidden_doc_title")]
    heading_pairs = [(r, c) for r, c in scored
                     if (c.get("expected_doc_title") or "").strip()]

    avg_latency = sum(r.latency_ms for r in results) // total

    failed = [
        {"case_id": r.case_id, "question": r.question, "detail": r.detail, "error": r.error,
         "group": r.group, "doc_rank": r.doc_rank}
        for r, _ in scored
        if not (r.intent_correct and r.doc_hit and r.tool_call_correct
                and r.has_citation and not r.forbidden_doc_leaked)
    ]
    timed_out_cases = [
        {"case_id": r.case_id, "question": r.question,
         "detail": r.detail, "latency_ms": r.latency_ms}
        for r in timeouts
    ]

    # 按组汇总
    groups: dict[str, list[CaseResult]] = {}
    for r, _ in scored:
        g = r.group or "default"
        groups.setdefault(g, []).append(r)
    by_group = {}
    for g, items in groups.items():
        ditems = [x for x in items if x.doc_rank >= 0 or (x.mrr == 0 and x.doc_hit)]
        # 有期望文档的组员才有 doc 指标
        doc_items = [x for x in items if x.mrr > 0 or x.doc_rank == -1]
        # 简化：组内所有 case 都计入 mrr（无期望时 mrr=1，会拉高——因此只统计 group 内
        # doc_rank 曾被计算过的（expected_title 有值）难以从 result 反推；
        # 用 doc_rank != 0 区分：无期望时我们设 doc_rank=-1 且 mrr=1.0，
        # 这里改为：mrr 组内平均时排除「未声明期望且 mrr==1 且 doc_hit」的情况不可靠。
        # 采用：组报告仅对 intent/tool 统计全量，doc/mrr 在报告总表用 doc_pairs。
        by_group[g] = {
            "count": len(items),
            "intent_accuracy": _rate(sum(1 for x in items if x.intent_correct), len(items)),
            "tool_call_accuracy": _rate(sum(1 for x in items if x.tool_call_correct), len(items)),
        }

    return EvalReport(
        total_cases=total,
        scored_cases=len(scored),
        timeout_count=len(timeouts),
        intent_accuracy=_rate(sum(1 for r, _ in scored if r.intent_correct), len(scored)),
        doc_hit_rate=_rate(sum(1 for r, _ in doc_pairs if r.doc_hit), len(doc_pairs)),
        recall_at_1=_rate(sum(1 for r, _ in doc_pairs if r.recall_at_1), len(doc_pairs)),
        mrr=round(sum(r.mrr for r, _ in doc_pairs) / len(doc_pairs), 4) if doc_pairs else 1.0,
        heading_hit_rate=_rate(sum(1 for r, _ in heading_pairs if r.heading_hit), len(heading_pairs)),
        tool_call_accuracy=_rate(sum(1 for r, _ in scored if r.tool_call_correct), len(scored)),
        citation_rate=_rate(sum(1 for r, _ in cite_pairs if r.has_citation), len(cite_pairs)),
        permission_pass_rate=_rate(
            sum(1 for r, _ in perm_pairs if not r.forbidden_doc_leaked), len(perm_pairs)
        ),
        avg_latency_ms=avg_latency,
        case_results=results,
        failed_cases=failed,
        timeout_cases=timed_out_cases,
        by_group=by_group,
    )
