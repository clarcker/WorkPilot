"""
Eval runner — 运行 golden cases 评测 RAG 工作流。

指标：
- intent_accuracy:    意图分类准确率
- doc_hit_rate:       检索命中率（仅统计声明了 expected_doc_title 的 case）
- tool_call_accuracy: 工具调用准确率（该调的调对、不该调的不调、参数合法、执行成功）
- citation_rate:      引用覆盖率（仅统计声明了 should_cite 的 case）
- permission_pass_rate: 权限负例通过率（受限文档未被召回）

设计要点：
1. 超时不算作"质量失败"。一条 case 超时意味着这一轮没有观测值，
   它会从各质量指标的分母里剔除，单独计入 timeout_count。
   （历史 bug：超时被记成 intent/doc/tool/citation 四项全错，
     且 str(asyncio.TimeoutError()) 是空字符串，失败原因整个丢失。）
2. 默认 skip_generation=True。四个指标都不依赖答案正文，而生成节点是整条
   链路最慢的一步（CPU 上 7B 模型约 100s/条），跳过后单条从 ~100s 降到几秒。
   需要端到端验证生成时传 skip_generation=False。
3. 默认 tool_dry_run=True，工具照常做权限与参数校验但不写库，
   避免每跑一次评测就往 it_tickets 里堆真工单。
4. 权限负例通过 case 的 as_user 字段固定身份运行——super_admin 会跳过
   全部权限过滤，用调用者身份跑权限负例恒失败。
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

# 单条 case 墙钟上限。skip_generation=True 时一条 RAG case 约 3~12s。
# 跑全量生成（skip_generation=False）时需要调大到几百秒。
DEFAULT_CASE_TIMEOUT = 90.0


@dataclass
class CaseResult:
    case_id: str
    question: str
    expected_intent: str
    actual_intent: str
    intent_correct: bool
    doc_hit: bool
    tool_call_correct: bool
    has_citation: bool
    forbidden_doc_leaked: bool  # True = 不该出现的文档被召回了
    latency_ms: int
    timed_out: bool = False     # True = 本轮无观测值，不参与质量指标
    error: Optional[str] = None
    detail: str = ""


@dataclass
class EvalReport:
    total_cases: int
    scored_cases: int            # 参与质量指标统计的 case 数（= total - timeout）
    timeout_count: int
    intent_accuracy: float
    doc_hit_rate: float
    tool_call_accuracy: float
    citation_rate: float
    permission_pass_rate: float
    avg_latency_ms: int
    case_results: list[CaseResult] = field(default_factory=list)
    failed_cases: list[dict] = field(default_factory=list)
    timeout_cases: list[dict] = field(default_factory=list)


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
    initial_state = RAGState(
        query=case["question"],
        user_id=run_user_id,
        user_role=run_user_role,
        user_dept_id=run_user_dept_id,
        conversation_history=[],
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
        skip_generation=skip_generation,
        gen_max_tokens=gen_max_tokens,
        tool_dry_run=tool_dry_run,
    )

    def _blank(timed_out: bool, err: str) -> CaseResult:
        return CaseResult(
            case_id=case["id"], question=case["question"],
            expected_intent=case.get("expected_intent", ""), actual_intent="",
            intent_correct=False, doc_hit=False, tool_call_correct=False,
            has_citation=False, forbidden_doc_leaked=False,
            latency_ms=int((time.time() - start) * 1000),
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

    # 文档命中：检查召回来源的文档名（测"召回了正确的文档"，而非在 chunk 文本里搜词）
    sources = final_state.get("sources", [])
    source_doc_names = [s.get("doc_name", "") for s in sources]
    doc_hit = True
    expected_title = case.get("expected_doc_title")
    if expected_title:
        doc_hit = any(expected_title in name for name in source_doc_names)

    # 工具调用：该调的调对、不该调的不调、参数合法、执行成功
    expected_tool = case.get("expected_tool")
    actual_tool = final_state.get("tool_name")
    actual_args = final_state.get("tool_args") or {}
    tool_success = final_state.get("tool_success")
    tool_error = final_state.get("tool_error")

    tool_detail = ""
    if expected_tool:
        if actual_tool != expected_tool:
            tool_call_correct = False
            tool_detail = f"工具: 期望={expected_tool}, 实际={actual_tool}"
        else:
            args_ok, args_msg = _args_match(case.get("expected_tool_args", {}), actual_args)
            # 只比对工具名会放过"名字对但参数全错"的调用——历史上模型生成过
            # {"问题类型": ...}，工具读的是 args["issue_type"]，工单从未真正创建
            exec_ok = (not case.get("expect_tool_success")) or tool_success is True
            tool_call_correct = args_ok and exec_ok
            if not args_ok:
                tool_detail = f"工具参数不符（实际={actual_args}）: {args_msg}"
            elif not exec_ok:
                tool_detail = f"工具 {actual_tool} 执行失败: {tool_error}"
    else:
        tool_call_correct = actual_tool is None
        if not tool_call_correct:
            tool_detail = f"工具: 期望不调用, 实际={actual_tool}({actual_args})"

    has_citation = len(sources) > 0 if case.get("should_cite") else True

    # 权限负例：不应召回 forbidden_doc_title 对应的文档
    forbidden_doc_leaked = False
    forbidden_title = case.get("forbidden_doc_title")
    if forbidden_title:
        forbidden_doc_leaked = any(forbidden_title in name for name in source_doc_names)

    detail_parts = []
    if not intent_correct:
        detail_parts.append(f"意图: 期望={expected_intent}, 实际={actual_intent}")
    if not doc_hit:
        detail_parts.append(
            f"未召回到期望文档: {expected_title}（实际召回: {source_doc_names or '无'}）"
        )
    if tool_detail:
        detail_parts.append(tool_detail)
    if not has_citation:
        detail_parts.append("缺少引用")
    if forbidden_doc_leaked:
        detail_parts.append(f"泄露受限文档: {forbidden_title}")

    return CaseResult(
        case_id=case["id"], question=case["question"],
        expected_intent=expected_intent, actual_intent=actual_intent,
        intent_correct=intent_correct, doc_hit=doc_hit,
        tool_call_correct=tool_call_correct, has_citation=has_citation,
        forbidden_doc_leaked=forbidden_doc_leaked,
        latency_ms=latency_ms, error=final_state.get("error"),
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

    # 超时 = 本轮没有观测值，不能算作质量失败，从各指标分母中剔除
    scored = [(r, c) for r, c in pairs if not r.timed_out]
    timeouts = [r for r in results if r.timed_out]

    doc_pairs = [(r, c) for r, c in scored if c.get("expected_doc_title")]
    cite_pairs = [(r, c) for r, c in scored if c.get("should_cite")]
    perm_pairs = [(r, c) for r, c in scored if c.get("forbidden_doc_title")]

    avg_latency = sum(r.latency_ms for r in results) // total

    failed = [
        {"case_id": r.case_id, "question": r.question, "detail": r.detail, "error": r.error}
        for r, _ in scored
        if not (r.intent_correct and r.doc_hit and r.tool_call_correct
                and r.has_citation and not r.forbidden_doc_leaked)
    ]
    timed_out_cases = [
        {"case_id": r.case_id, "question": r.question,
         "detail": r.detail, "latency_ms": r.latency_ms}
        for r in timeouts
    ]

    return EvalReport(
        total_cases=total,
        scored_cases=len(scored),
        timeout_count=len(timeouts),
        intent_accuracy=_rate(sum(1 for r, _ in scored if r.intent_correct), len(scored)),
        doc_hit_rate=_rate(sum(1 for r, _ in doc_pairs if r.doc_hit), len(doc_pairs)),
        tool_call_accuracy=_rate(sum(1 for r, _ in scored if r.tool_call_correct), len(scored)),
        citation_rate=_rate(sum(1 for r, _ in cite_pairs if r.has_citation), len(cite_pairs)),
        permission_pass_rate=_rate(
            sum(1 for r, _ in perm_pairs if not r.forbidden_doc_leaked), len(perm_pairs)
        ),
        avg_latency_ms=avg_latency,
        case_results=results,
        failed_cases=failed,
        timeout_cases=timed_out_cases,
    )
