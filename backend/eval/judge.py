"""Q3 LLM-as-judge：答案质量评测。

裁判输入：用户问题、参考资料片段、expected_points、模型答案。
裁判输出 JSON：faithfulness / points_covered / hallucinated_claims /
refusal_correct / citation_correct。
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from core.config import settings
from core.logger import logger
from services.llm_client import chat_complete, resolve_provider


def _judge_model_name() -> tuple[str, str]:
    """返回 (model_name, is_external)。"""
    provider = resolve_provider("super_admin") if settings.openai_api_key else resolve_provider(None)
    # 裁判优先外部（可信度高）；无 key 时用全局 provider
    if settings.openai_api_key and settings.openai_api_key.strip():
        # 强制走外部时 model 名取 openai_model
        return settings.openai_model, True
    if settings.llm_provider == "ollama":
        return settings.ollama_chat_model, False
    return settings.openai_model, bool(settings.openai_api_key)


_JUDGE_SYSTEM = None


def _judge_system() -> str:
    try:
        from services.prompt_loader import get_prompt
        return get_prompt("judge.md")
    except Exception:
        return _FALLBACK_JUDGE_SYSTEM


_FALLBACK_JUDGE_SYSTEM = """\
你是企业知识库问答的评审员。只根据【参考资料】与【工具结果】判断模型答案质量，不要用自己的知识补充。
输出严格 JSON：faithfulness/points_covered/hallucinated_claims/refusal_correct/citation_correct/notes。
"""


def _build_judge_user(
    question: str,
    answer: str,
    sources: list[dict],
    expected_points: list[str],
    expected_refusal: bool,
    expected_doc_title: str,
    tool_name: str | None = None,
    tool_result: dict | None = None,
    tool_success: bool | None = None,
    tool_error: str | None = None,
) -> str:
    refs = []
    for i, s in enumerate(sources or [], 1):
        name = s.get("doc_name") or "未知"
        text = (s.get("chunk_text") or s.get("content") or "")[:500]
        life = s.get("lifecycle") or ""
        note = s.get("lifecycle_note") or ""
        tag = f" [{life}]" if life and life != "effective" else ""
        if note:
            tag += f" ({note})"
        refs.append(f"[资料 {i}] {name}{tag}\n{text}")
    ref_block = "\n\n".join(refs) if refs else "（无参考资料）"

    tool_block = "（本条未调用工具）"
    if tool_name:
        import json as _json
        try:
            res_s = _json.dumps(tool_result, ensure_ascii=False, indent=2) if tool_result is not None else "null"
        except (TypeError, ValueError):
            res_s = str(tool_result)
        status = "success" if tool_success else f"failed ({tool_error or 'unknown'})"
        tool_block = (
            f"tool={tool_name}\nstatus={status}\nresult:\n{res_s[:2000]}"
        )

    points = "\n".join(f"- {p}" for p in expected_points) if expected_points else "（无）"
    return (
        f"【用户问题】\n{question}\n\n"
        f"【参考资料】\n{ref_block}\n\n"
        f"【工具结果】\n{tool_block}\n\n"
        f"【必须覆盖的要点 expected_points】\n{points}\n\n"
        f"【expected_refusal】{str(expected_refusal).lower()}\n"
        f"【expected_doc_title】{expected_doc_title or '（无）'}\n\n"
        f"【模型答案】\n{answer or '（空答案）'}\n\n"
        "请输出 JSON。"
    )


def _parse_judge_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    # 容错：截取第一个 { 到最后一个 }
    if not text.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            text = m.group(0)
    data = json.loads(text)
    faith = data.get("faithfulness")
    try:
        faith = max(1, min(5, int(faith)))
    except (TypeError, ValueError):
        faith = 3
    covered = data.get("points_covered_count")
    expected_n = data.get("expected_points_count")
    if covered is None or expected_n is None:
        # 从 "m/n" 解析
        pcs = str(data.get("points_covered") or "")
        m = re.match(r"(\d+)\s*/\s*(\d+)", pcs)
        if m:
            covered, expected_n = int(m.group(1)), int(m.group(2))
        else:
            covered, expected_n = 0, 0
    claims = data.get("hallucinated_claims") or []
    if isinstance(claims, str):
        claims = [claims] if claims.strip() else []
    return {
        "faithfulness": faith,
        "points_covered": f"{int(covered)}/{int(expected_n)}",
        "points_covered_count": int(covered),
        "expected_points_count": int(expected_n),
        "hallucinated_claims": [str(c) for c in claims if str(c).strip()],
        "refusal_correct": bool(data.get("refusal_correct", False)),
        "citation_correct": bool(data.get("citation_correct", True)),
        "notes": data.get("notes") or "",
    }


async def judge_answer(
    question: str,
    answer: str,
    sources: list[dict],
    expected_points: list[str] | None = None,
    expected_refusal: bool = False,
    expected_doc_title: str = "",
    user_role: str | None = "super_admin",
    tool_name: str | None = None,
    tool_result: dict | None = None,
    tool_success: bool | None = None,
    tool_error: str | None = None,
) -> dict[str, Any]:
    """调用裁判模型，返回结构化 judge JSON。失败时返回 error 字段。"""
    model_name, is_external = _judge_model_name()
    # 有外部 key 时强制用外部（经 R0 脱敏）；否则跟 user_role / 全局配置
    role_for_llm = "super_admin" if is_external else (user_role or None)

    messages = [
        {"role": "system", "content": _judge_system()},
        {
            "role": "user",
            "content": _build_judge_user(
                question=question,
                answer=answer,
                sources=sources,
                expected_points=expected_points or [],
                expected_refusal=expected_refusal,
                expected_doc_title=expected_doc_title or "",
                tool_name=tool_name,
                tool_result=tool_result,
                tool_success=tool_success,
                tool_error=tool_error,
            ),
        },
    ]
    try:
        # 若配置了外部 key，绕过 role 路由直接用 openai（裁判可信度）
        if is_external:
            from services.llm_client import _openai_complete, _prepare_outbound
            msgs = _prepare_outbound(messages, "openai_compatible")
            raw = await _openai_complete(msgs, temperature=0, max_tokens=600)
        else:
            raw = await chat_complete(
                messages, temperature=0, max_tokens=600, user_role=role_for_llm
            )
        parsed = _parse_judge_json(raw)
        parsed["judge_model"] = model_name
        parsed["judge_external"] = is_external
        if not is_external:
            parsed["trust_note"] = "本地裁判，可信度低"
        return parsed
    except Exception as exc:
        logger.warning(f"[judge] 裁判失败: {type(exc).__name__}: {exc}")
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "faithfulness": None,
            "points_covered": "0/0",
            "points_covered_count": 0,
            "expected_points_count": len(expected_points or []),
            "hallucinated_claims": [],
            "refusal_correct": False,
            "citation_correct": False,
            "judge_model": model_name,
            "judge_external": is_external,
        }


def aggregate_judges(case_judges: list[dict]) -> dict[str, Any]:
    """汇总 judge 结果 → eval_runs 字段。"""
    valid = [j for j in case_judges if j and not j.get("error") and j.get("faithfulness") is not None]
    n = len(valid)
    if n == 0:
        return {
            "judge_model": None,
            "faithfulness_avg": None,
            "points_coverage": None,
            "hallucination_count": 0,
            "refusal_correct_rate": None,
            "local_judge": False,
        }
    faith = sum(j["faithfulness"] for j in valid) / n
    covered = sum(j.get("points_covered_count") or 0 for j in valid)
    expected = sum(j.get("expected_points_count") or 0 for j in valid)
    hallu = sum(len(j.get("hallucinated_claims") or []) for j in valid)
    refusal_cases = [j for j in valid if j.get("_expected_refusal")]
    refusal_rate = (
        sum(1 for j in refusal_cases if j.get("refusal_correct")) / len(refusal_cases)
        if refusal_cases
        else None
    )
    model = valid[0].get("judge_model")
    local = not valid[0].get("judge_external", True)
    return {
        "judge_model": model,
        "faithfulness_avg": round(faith, 4),
        "points_coverage": round(covered / expected, 4) if expected else None,
        "hallucination_count": hallu,
        "refusal_correct_rate": refusal_rate,
        "local_judge": local,
    }
