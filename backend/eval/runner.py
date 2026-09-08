"""
Eval runner — 运行 golden cases 评测 RAG 工作流。

指标：
- intent_accuracy: 意图分类准确率
- doc_hit_rate: 检索命中率
- tool_call_accuracy: 工具调用准确率
- citation_rate: 引用覆盖率
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from graph.state import RAGState
from graph.workflow import rag_graph

_CASES_PATH = Path(__file__).parent / "cases.json"


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
    latency_ms: int
    error: Optional[str] = None
    detail: str = ""


@dataclass
class EvalReport:
    total_cases: int
    intent_accuracy: float
    doc_hit_rate: float
    tool_call_accuracy: float
    citation_rate: float
    avg_latency_ms: int
    case_results: list[CaseResult] = field(default_factory=list)
    failed_cases: list[dict] = field(default_factory=list)


def load_cases() -> list[dict]:
    with open(_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def run_case(case: dict, user_id: int = 1, user_role: str = "employee",
                   user_dept_id: int | None = 1) -> CaseResult:
    start = time.time()
    initial_state = RAGState(
        query=case["question"],
        user_id=user_id,
        user_role=user_role,
        user_dept_id=user_dept_id,
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
    )
    try:
        final_state = await asyncio.wait_for(rag_graph.ainvoke(initial_state), timeout=60.0)
    except Exception as exc:
        return CaseResult(
            case_id=case["id"], question=case["question"],
            expected_intent=case.get("expected_intent", ""), actual_intent="",
            intent_correct=False, doc_hit=False, tool_call_correct=False,
            has_citation=False, latency_ms=int((time.time() - start) * 1000),
            error=str(exc),
        )

    latency_ms = int((time.time() - start) * 1000)
    actual_intent = final_state.get("intent", "")
    expected_intent = case.get("expected_intent", "")
    intent_correct = actual_intent == expected_intent

    doc_hit = True
    expected_keywords = case.get("expected_doc_keywords", [])
    if expected_keywords:
        chunks = final_state.get("retrieved_chunks", [])
        chunk_texts = " ".join(c.get("content", "") for c in chunks)
        doc_hit = any(kw in chunk_texts for kw in expected_keywords)

    tool_call_correct = True
    expected_tool = case.get("expected_tool")
    if expected_tool:
        tool_call_correct = final_state.get("tool_name") == expected_tool

    has_citation = len(final_state.get("sources", [])) > 0 if case.get("should_cite") else True

    detail_parts = []
    if not intent_correct:
        detail_parts.append(f"意图: 期望={expected_intent}, 实际={actual_intent}")
    if not doc_hit:
        detail_parts.append(f"文档未命中关键词: {expected_keywords}")
    if not tool_call_correct:
        detail_parts.append(f"工具: 期望={expected_tool}, 实际={final_state.get('tool_name')}")
    if not has_citation:
        detail_parts.append("缺少引用")

    return CaseResult(
        case_id=case["id"], question=case["question"],
        expected_intent=expected_intent, actual_intent=actual_intent,
        intent_correct=intent_correct, doc_hit=doc_hit,
        tool_call_correct=tool_call_correct, has_citation=has_citation,
        latency_ms=latency_ms, detail="; ".join(detail_parts),
    )


async def run_eval(user_id: int = 1, user_role: str = "employee",
                   user_dept_id: int | None = 1) -> EvalReport:
    cases = load_cases()
    results = []
    for case in cases:
        result = await run_case(case, user_id, user_role, user_dept_id)
        results.append(result)

    total = len(results)
    if total == 0:
        return EvalReport(total_cases=0, intent_accuracy=0, doc_hit_rate=0,
                          tool_call_accuracy=0, citation_rate=0, avg_latency_ms=0)

    intent_correct = sum(1 for r in results if r.intent_correct)
    doc_hits = sum(1 for r in results if r.doc_hit)
    tool_cases = [r for r in results if r.case_id in
                  [c["id"] for c in cases if c.get("expected_tool")]]
    tool_correct = sum(1 for r in tool_cases if r.tool_call_correct) if tool_cases else 0
    citation_ok = sum(1 for r in results if r.has_citation)
    avg_latency = sum(r.latency_ms for r in results) // total

    failed = [
        {"case_id": r.case_id, "question": r.question, "detail": r.detail}
        for r in results
        if not (r.intent_correct and r.doc_hit and r.tool_call_correct and r.has_citation)
    ]

    return EvalReport(
        total_cases=total, intent_accuracy=intent_correct / total,
        doc_hit_rate=doc_hits / total,
        tool_call_accuracy=tool_correct / len(tool_cases) if tool_cases else 1.0,
        citation_rate=citation_ok / total, avg_latency_ms=avg_latency,
        case_results=results, failed_cases=failed,
    )