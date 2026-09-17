"""
LangGraph RAG 工作流节点函数。

节点顺序（anonymize 与 classify_intent 并行）：

  START ──┬──► anonymize
          └──► classify_intent
               ↓ (两者均完成后 sync_node 汇合)
             sync
               ├─ chitchat ──► generate_chitchat ──► END
               └─ rag      ──► retrieve_docs ──► generate_answer ──► END

每个节点接收 RAGState，返回更新该状态的 dict（LangGraph 自动 merge）。
"""
from __future__ import annotations

import re
import time

from core.logger import logger
from graph.state import RAGState


def describe_exc(exc: BaseException) -> str:
    """
    异常的可读描述。

    httpx.ReadTimeout / asyncio.TimeoutError 的 str() 都是空字符串，
    直接拼进消息里会得到"模型调用失败："这种没有任何信息的报错。
    """
    msg = str(exc).strip()
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__
from services.embedder import get_embedding
from services.llm_client import chat_complete, chat_stream
from services.retriever import retrieve


# ══════════════════════════════════════════════
#  1. 脱敏节点（仅产出 anonymized_query 供 trace；真正脱敏在 llm_client 出口）
# ══════════════════════════════════════════════

from core.anonymizer import anonymize_text


async def anonymize_node(state: RAGState) -> dict:
    """记录脱敏后的 query（trace 用）。出网脱敏由 llm_client._prepare_outbound 统一处理。"""
    return {"anonymized_query": anonymize_text(state["query"])}


# ══════════════════════════════════════════════
#  2. 意图分类节点（与 anonymize 并行执行）
# ══════════════════════════════════════════════

# 明确的闲聊模式——正则快速匹配，跳过 LLM 调用
_CHITCHAT_PATTERNS = [
    r"^你好$|^hi$|^hello$|^嗨$|^哈喽$|^早上好$|^下午好$|^晚上好$",
    r"^谢谢$|^感谢$|^thank\s*you$|^thanks$",
    r"^再见$|^拜拜$|^bye$|^goodbye$|^下次见$",
    r"^(好的|ok|okay|收到|明白|了解)\s*[！!。.,，]*$",
    r"^(哈哈|嗯|哦|啊|嘻嘻|嘿嘿)\s*[！!。.,，]*$",
    r"^你是谁$|^你叫什么$|^你是什么$",
    r"^在吗$|^在不在$",
]


def _is_obvious_chitchat(query: str) -> bool:
    q = query.strip()
    for pat in _CHITCHAT_PATTERNS:
        if re.match(pat, q, re.IGNORECASE):
            return True
    return False


def _classify_by_keywords(query: str) -> str:
    """LLM 不可用时的降级方案。"""
    rag_keywords = [
        "制度", "规范", "流程", "政策", "规定", "规则",
        "报销", "请假", "考勤", "薪资", "工资", "福利",
        "培训", "安全", "合规", "文档", "手册", "指南",
        "入职", "离职", "转正", "出差", "年假", "补贴", "额度",
        "设备", "电脑", "网络", "报修", "维修", "工单", "权限",
        "怎么", "如何", "什么", "哪些", "多少", "几天",
        "可以", "能", "需要", "必须", "应该",
        "公司", "部门", "员工", "领导", "管理",
    ]
    q = query.strip()
    for kw in rag_keywords:
        if kw in q:
            return "rag"
    return "chitchat" if len(q) < 5 else "rag"


async def query_understand_node(state: RAGState) -> dict:
    """
    R1：一次调用输出 intent + rewrite_query，替代 classify_intent 与 retrieve 内的改写。

    正则快速通道保留；JSON 失败降级：intent 用关键词，rewrite 用原 query。
    无历史时只分类，rewrite=原 query。
    """
    query = state["query"]
    history = state.get("conversation_history") or []
    user_role = state.get("user_role")
    node_steps = list(state.get("node_steps") or [])

    if _is_obvious_chitchat(query):
        return {
            "intent": "chitchat",
            "rewritten_query": query,
            "node_steps": node_steps + [{
                "node": "query_understand",
                "output_summary": "regex→chitchat",
                "latency_ms": 0,
            }],
        }

    hist_text = ""
    if history:
        hist_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-4:])

    import json as _json

    system = (
        "你是企业助手的查询理解模块。根据用户最新问题输出 JSON：\n"
        '{"intent": "rag" 或 "chitchat", "rewrite_query": "可独立检索的完整问题"}\n\n'
        "规则：\n"
        "- intent=chitchat：纯日常闲聊/问候/与公司无关\n"
        "- intent=rag：公司制度、流程、业务办理（报销/请假/IT/工单等）\n"
        "- rewrite_query：若有对话历史，把指代补全；无历史或问题已完整则原样输出\n"
        "只输出 JSON，不要解释。"
    )
    user_content = f"对话历史：\n{hist_text or '（无）'}\n\n最新问题：{query}"

    t0 = time.time()
    intent = _classify_by_keywords(query)
    rewritten = query
    try:
        raw = await chat_complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
            temperature=0, max_tokens=160, user_role=user_role,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = _json.loads(raw)
        if data.get("intent") in ("rag", "chitchat"):
            intent = data["intent"]
        rq = (data.get("rewrite_query") or "").strip().strip('"')
        if 2 <= len(rq) <= 200:
            rewritten = rq
    except Exception as exc:
        logger.warning(f"[query_understand] 解析失败，降级: {describe_exc(exc)}")

    latency = int((time.time() - t0) * 1000)
    node_steps.append({
        "node": "query_understand",
        "output_summary": f"intent={intent} rewrite={rewritten[:60]!r}",
        "latency_ms": latency,
    })
    logger.debug(f"[query_understand] {intent} | rewrite={rewritten[:60]!r}")
    return {
        "intent": intent,
        "rewritten_query": rewritten,
        "node_steps": node_steps,
    }


# 兼容旧图名
classify_intent_node = query_understand_node


# ══════════════════════════════════════════════
#  3. 汇聚节点（fan-in 同步点）
# ══════════════════════════════════════════════

async def sync_node(state: RAGState) -> dict:
    """等待 anonymize 和 query_understand 均完成后的汇聚点，不修改状态。"""
    return {}


# ══════════════════════════════════════════════
#  4. 检索节点
# ══════════════════════════════════════════════

async def _rewrite_query(query: str, history: list, user_role: str | None = None) -> str:
    """多轮追问改写：把「那出差补贴呢」补全成语义完整问题。失败降级原 query。"""
    if not history:
        return query
    hist_text = "\n".join(f"{h['role']}: {h['content']}" for h in history[-4:])
    messages = [
        {
            "role": "system",
            "content": (
                "根据对话历史，把用户最新的问题改写成独立、完整、可检索的一句话。"
                "只输出改写后的问题，不要解释。若原问题已完整，原样输出。"
            ),
        },
        {"role": "user", "content": f"对话历史：\n{hist_text}\n\n最新问题：{query}"},
    ]
    try:
        rewritten = await chat_complete(
            messages, temperature=0, max_tokens=80, user_role=user_role,
        )
        rewritten = (rewritten or "").strip().strip('"')
        if 2 <= len(rewritten) <= 200:
            return rewritten
    except Exception as exc:
        logger.debug(f"[rewrite] 改写失败，使用原 query: {describe_exc(exc)}")
    return query


async def retrieve_docs_node(state: RAGState) -> dict:
    """
    用 query_understand 产出的 rewritten_query 做混合检索（向量 + 关键词 RRF）。
    检索完成后立即通过 SSE 推送 sources。
    """
    query = state["query"]
    rewritten = state.get("rewritten_query") or query
    queue = state.get("token_queue")
    node_steps = list(state.get("node_steps") or [])

    t0 = time.time()
    embed_text = rewritten or query

    try:
        query_vec = await get_embedding(embed_text)
        chunks = await retrieve(
            query_embedding=query_vec,
            query_text=embed_text,
            user_id=state["user_id"],
            user_dept_id=state["user_dept_id"],
            user_role=state["user_role"],
        )
        logger.debug(f"[retrieve_docs] 检索到 {len(chunks)} 个 chunk | q={embed_text[:40]!r}")
        chunk_dicts = [dict(c) for c in chunks]

        if queue and chunk_dicts:
            sources = _build_sources(chunk_dicts)
            if sources:
                await queue.put({"type": "sources", "content": sources})

        node_steps.append({
            "node": "retrieve_docs",
            "output_summary": f"rewritten={rewritten[:80]!r} hits={len(chunk_dicts)}",
            "latency_ms": int((time.time() - t0) * 1000),
        })
        return {
            "retrieved_chunks": chunk_dicts,
            "node_steps": node_steps,
        }
    except Exception as exc:
        logger.error(f"[retrieve_docs] 检索失败: {describe_exc(exc)}", exc_info=True)
        node_steps.append({
            "node": "retrieve_docs",
            "output_summary": "error",
            "latency_ms": int((time.time() - t0) * 1000),
            "error": describe_exc(exc),
        })
        return {
            "retrieved_chunks": [],
            "node_steps": node_steps,
            "error": f"检索失败: {describe_exc(exc)}",
        }


def llm_query_for_completion(state: RAGState) -> str:
    """
    送给 LLM 的用户问题。脱敏在 llm_client 出口统一做（R0），
    这里始终返回原文，保证本地模型能用姓名/工号做上下文。
    """
    return state["query"]


# ══════════════════════════════════════════════
#  5. RAG 回答生成节点
# ══════════════════════════════════════════════

_RAG_SYSTEM_PROMPT = """\
你是企业内部知识库助手 WorkPilot。根据下方参考资料回答员工问题。

规则：
- 只引用参考资料中的信息，不要编造内容
- 若参考资料中没有相关内容，直接如实说明，并建议员工换关键词重试或联系相关部门
- 回答简洁准确，使用 Markdown 格式
{tool_section}
【参考资料】
{context}
"""

_TOOL_SUCCESS_SECTION = """
【工具查询结果】
系统已为当前用户执行工具 `{tool_name}`，结果如下（这是真实业务数据，回答时必须结合）：
```json
{tool_result}
```
- 若用户在问个人数据（额度、工单、员工信息），优先用上方工具结果回答具体数字/单号
- 制度说明仍可参考下方资料，两者互补
"""

_TOOL_FAIL_SECTION = """
【工具执行情况】
系统尝试调用工具 `{tool_name}` 但未成功：{tool_error}
- 不要编造工具本应返回的数据
- 可基于下方制度资料说明规则，并建议用户联系相关部门或稍后重试
"""


def _build_tool_section(state: RAGState) -> str:
    """把工具执行结果拼进 system prompt，让 LLM 正文能引用真实数据。"""
    tool_name = state.get("tool_name")
    if not tool_name:
        return ""

    tool_result = state.get("tool_result")
    tool_error  = state.get("tool_error") or state.get("permission_denied")
    tool_success = state.get("tool_success")

    if tool_success and tool_result is not None:
        import json as _json
        try:
            result_str = _json.dumps(tool_result, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            result_str = str(tool_result)
        return _TOOL_SUCCESS_SECTION.format(tool_name=tool_name, tool_result=result_str)

    reason = tool_error or "未知原因"
    return _TOOL_FAIL_SECTION.format(tool_name=tool_name, tool_error=reason)


def _build_context(chunks: list[dict]) -> str:
    if not chunks:
        return "（本次检索未找到相关文档）"
    parts = []
    for i, chunk in enumerate(chunks, 1):
        doc_name = chunk.get("doc_name", "未知文档")
        heading  = chunk.get("heading", "")
        page_no  = chunk.get("page_no")
        loc = f" > {heading}" if heading else ""
        if page_no:
            loc += f"（第 {page_no} 页）"
        parts.append(f"[资料 {i}] 来源：{doc_name}{loc}\n{chunk['content']}")
    return "\n\n---\n\n".join(parts)


def _build_sources(chunks: list[dict]) -> list[dict]:
    """每个 doc 只保留一条引用（去重）。"""
    seen: set[int] = set()
    sources = []
    for chunk in chunks:
        doc_id = chunk["doc_id"]
        if doc_id not in seen:
            seen.add(doc_id)
            sources.append({
                "doc_id":     doc_id,
                "doc_name":   chunk.get("doc_name", ""),
                "chunk_id":   chunk["chunk_id"],
                "heading":    chunk.get("heading"),
                "page_no":    chunk.get("page_no"),
                "score":      round(chunk.get("score", 0), 4),
                "chunk_text": chunk.get("content", "")[:500],
            })
    return sources


async def generate_answer_node(state: RAGState) -> dict:
    """
    调用 LLM 生成 RAG 回答并流式推送 token。
    检索结果为空时 LLM 会根据系统提示如实说明，不再需要单独的兜底节点。
    工具已执行时，把 tool_result / tool_error 一并注入 prompt。
    """
    chunks  = state.get("retrieved_chunks", [])
    history = state.get("conversation_history", [])
    queue   = state.get("token_queue")

    # 评测回归只看 intent / sources / tool_name，不需要答案正文。
    # 生成是整条链路最慢的一步（CPU 上 7B 模型 ~100s/条），跳过可把
    # 单条耗时从 ~100s 降到几秒，避免评测被自身超时判失败。
    if state.get("skip_generation"):
        sources = _build_sources(chunks)
        if queue:
            await queue.put(None)
        return {"full_answer": "", "sources": sources}

    context     = _build_context(chunks)
    tool_section = _build_tool_section(state)
    system_msg  = _RAG_SYSTEM_PROMPT.format(context=context, tool_section=tool_section)
    sources     = _build_sources(chunks)

    messages = [{"role": "system", "content": system_msg}]
    for h in history[-6:]:   # 最近 3 轮历史（6 条）
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": llm_query_for_completion(state)})

    max_tokens = state.get("gen_max_tokens") or 2048
    full_answer = ""
    try:
        async for token in chat_stream(
            messages, temperature=0.3, max_tokens=max_tokens,
            user_role=state.get("user_role"),
        ):
            full_answer += token
            if queue:
                await queue.put({"type": "token", "content": token})
    except Exception as exc:
        error_msg = f"模型调用失败：{describe_exc(exc)}"
        logger.error(f"[generate_answer] {error_msg}")
        if queue:
            await queue.put({"type": "error", "content": error_msg})
            await queue.put(None)
        # 检索此时已经成功了，sources 必须保留：
        # 前端已经收到过 sources 事件，清空会让引用面板凭空消失；
        # 评测里 doc_hit 是检索指标，被生成失败连坐会得出错误结论。
        return {"full_answer": full_answer, "sources": sources, "error": error_msg}

    logger.debug(f"[generate_answer] 生成完毕，{len(full_answer)} 字符")
    if queue:
        await queue.put(None)
    return {"full_answer": full_answer, "sources": sources}


# ══════════════════════════════════════════════
#  6. 闲聊回答生成节点
# ══════════════════════════════════════════════

_CHITCHAT_SYSTEM = (
    "你是企业内部知识库助手 WorkPilot，性格友好自然。"
    "用户正在闲聊，请简短回复（1-2 句话），直接输出纯文本，不要使用 Markdown。"
    "不要主动引导用户去查文档。"
)


async def generate_chitchat_node(state: RAGState) -> dict:
    """直接调用 LLM 处理闲聊，流式推送 token。"""
    queue = state.get("token_queue")

    if state.get("skip_generation"):
        if queue:
            await queue.put(None)
        return {"full_answer": "", "sources": []}

    messages = [
        {"role": "system", "content": _CHITCHAT_SYSTEM},
        {"role": "user",   "content": state["query"]},
    ]
    full_answer = ""
    try:
        async for token in chat_stream(
            messages, temperature=0.7, max_tokens=150,
            user_role=state.get("user_role"),
        ):
            full_answer += token
            if queue:
                await queue.put({"type": "token", "content": token})
    except Exception as exc:
        error_msg = f"模型调用失败：{describe_exc(exc)}"
        logger.error(f"[generate_chitchat] {error_msg}")
        if queue:
            await queue.put({"type": "error", "content": error_msg})
            await queue.put(None)
        return {"full_answer": "", "sources": [], "error": error_msg}

    if queue:
        await queue.put(None)
    return {"full_answer": full_answer, "sources": []}


# ══════════════════════════════════════════════
#  路由函数（条件边）
# ══════════════════════════════════════════════

def route_after_sync(state: RAGState) -> str:
    """sync_node 完成后：chitchat → generate_chitchat；rag → retrieve_docs。"""
    return "chitchat" if state.get("intent") == "chitchat" else "rag"


# ══════════════════════════════════════════════
#  7. 工具决策节点
# ══════════════════════════════════════════════

_TOOL_DECISION_PROMPT = """\
你是企业内部助手。根据用户问题判断是否需要调用工具。

可用工具：
{tools_desc}

已执行的工具及结果（供你决定是否还需要下一步）：
{tool_history_desc}

规则：
- 用户要求查询自己的具体数据（员工信息、报销额度）或要求办理业务（报修、提工单、提交报销）时，才调用工具
- 只是询问制度/流程/规定（如"报销制度是什么"、"设备维修怎么申请"），不要调用工具
- 报销提交流程：先 precheck_reimbursement，再 submit_reimbursement_request（若预审已通过且信息齐全）
- 已成功调用过的工具不要重复调用；缺信息时不要硬调提交类工具
- tool_args 的键必须严格使用上面列出的英文参数名，不要翻译成中文，不要自创参数名
- 必填参数无法从用户问题中确定时，不要调用该工具
- 回复 JSON：{{"need_tool": true, "tool_name": "xxx", "tool_args": {{...}}}} 或 {{"need_tool": false}}

只回复 JSON。"""


def _format_tool_for_prompt(t: dict) -> str:
    """把工具的 JSON Schema 渲染成 LLM 可读的参数说明。

    参数名必须出现在提示词里，否则模型会自己编键名（曾生成 {"问题类型": ...}
    而工具读的是 args["issue_type"]，导致工单永远创建失败）。
    """
    schema = t.get("parameters") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])

    if not props:
        params_desc = "无参数"
    else:
        lines = []
        for k, v in props.items():
            bits = [v.get("type", "string")]
            bits.append("必填" if k in required else "可选")
            if v.get("enum"):
                bits.append("取值: " + "/".join(str(e) for e in v["enum"]))
            if v.get("description"):
                bits.append(v["description"])
            lines.append(f"    - {k} ({', '.join(bits)})")
        params_desc = "\n" + "\n".join(lines)

    return f"- {t['name']}: {t['description']}\n  参数：{params_desc}"


async def decide_tool_node(state: RAGState) -> dict:
    from tools.base import tool_registry
    import json as _json

    if state.get("intent") == "chitchat":
        return {"need_tool": False}

    # 已确认 / 缺槽位 / 达到步数上限 → 不再决策新工具
    if state.get("requires_confirmation") or state.get("missing_slots"):
        return {"need_tool": False}
    max_steps = int(state.get("max_tool_steps") or 4)
    if int(state.get("tool_step") or 0) >= max_steps:
        return {"need_tool": False}

    tools_desc_parts = []
    for t in tool_registry.get_tools_for_prompt(state.get("user_role", "employee")):
        tools_desc_parts.append(_format_tool_for_prompt(t))

    if not tools_desc_parts:
        return {"need_tool": False}

    history = state.get("tool_history") or []
    if history:
        hist_lines = [
            f"- {h.get('name')} success={h.get('success')} result={str(h.get('result'))[:200]}"
            for h in history[-4:]
        ]
        tool_history_desc = "\n".join(hist_lines)
    else:
        tool_history_desc = "（尚未调用任何工具）"

    tools_desc = "\n".join(tools_desc_parts)
    messages = [
        {"role": "system", "content": _TOOL_DECISION_PROMPT.format(
            tools_desc=tools_desc, tool_history_desc=tool_history_desc,
        )},
        {"role": "user", "content": llm_query_for_completion(state)},
    ]

    try:
        answer = await chat_complete(
            messages, temperature=0, max_tokens=200,
            user_role=state.get("user_role"),
        )
        answer = answer.strip()
        if answer.startswith("```"):
            answer = answer.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        decision = _json.loads(answer)
        need_tool = decision.get("need_tool", False)
        tool_name = decision.get("tool_name")
        tool_args = decision.get("tool_args", {})
        if need_tool and tool_name and tool_registry.get(tool_name):
            logger.debug(f"[decide_tool] 调用工具: {tool_name}({tool_args})")
            return {"need_tool": True, "tool_name": tool_name, "tool_args": tool_args}
        return {"need_tool": False}
    except Exception as exc:
        logger.warning(f"[decide_tool] 解析失败: {describe_exc(exc)}")
        return {"need_tool": False}


# ══════════════════════════════════════════════
#  8. 工具执行节点
# ══════════════════════════════════════════════

async def execute_tool_node(state: RAGState) -> dict:
    from tools.base import tool_registry, ToolContext
    from core.config import settings
    from core.anonymizer import contains_placeholder

    tool_name = state.get("tool_name")
    tool_args = dict(state.get("tool_args") or {})
    queue = state.get("token_queue")
    tool_step = int(state.get("tool_step") or 0)
    tool_history = list(state.get("tool_history") or [])
    node_steps = list(state.get("node_steps") or [])

    if not tool_name:
        return {"tool_result": None, "tool_success": None, "tool_error": None}

    # 脱敏占位符参数视为无效（R0 边界）
    for k, v in list(tool_args.items()):
        if isinstance(v, str) and contains_placeholder(v):
            tool_args.pop(k)

    ctx = ToolContext(user_id=state["user_id"], user_role=state.get("user_role", "employee"),
                     user_dept_id=state.get("user_dept_id"),
                     dry_run=bool(state.get("tool_dry_run")))

    start = time.time()
    result = await tool_registry.execute(
        tool_name, tool_args, ctx, timeout=settings.tool_timeout
    )
    latency_ms = int((time.time() - start) * 1000)

    tool_history.append({
        "name": tool_name,
        "args": tool_args,
        "result": result.data if result.success else None,
        "success": result.success,
        "error": result.error or result.deny_reason,
        "latency_ms": latency_ms,
    })
    node_steps.append({
        "node": "execute_tool",
        "output_summary": f"{tool_name} success={result.success} conf={result.requires_confirmation}",
        "latency_ms": latency_ms,
        "error": result.error,
    })

    if queue:
        payload = {
            "tool_name": tool_name, "tool_args": tool_args,
            "allowed": result.deny_reason is None,
            "deny_reason": result.deny_reason,
            "result": result.data if result.success else None,
            "error": result.error, "latency_ms": latency_ms,
            "requires_confirmation": result.requires_confirmation,
            "missing_slots": result.missing_slots,
        }
        await queue.put({"type": "tool_call", "content": payload})
        if result.requires_confirmation and result.success:
            await queue.put({
                "type": "confirm_required",
                "content": {
                    "tool_name": tool_name,
                    "payload": result.data,
                },
            })
        if result.missing_slots:
            await queue.put({
                "type": "form_incomplete",
                "content": {"missing_slots": result.missing_slots, "message": (result.data or {}).get("message")},
            })

    update = {
        "tool_step": tool_step + 1,
        "tool_history": tool_history,
        "node_steps": node_steps,
        "requires_confirmation": bool(result.requires_confirmation and result.success),
        "confirm_payload": result.data if result.requires_confirmation and result.success else None,
        "missing_slots": result.missing_slots,
    }

    if result.success:
        update.update({"tool_result": result.data, "tool_success": True, "tool_error": None})
        return update

    reason = result.error or result.deny_reason
    logger.warning(f"[execute_tool] {tool_name} 执行失败: {reason} | args={tool_args}")
    update.update({
        "tool_result": None, "tool_success": False, "tool_error": reason,
        "error": reason, "permission_denied": result.deny_reason,
    })
    return update


def route_after_decide_tool(state: RAGState) -> str:
    if state.get("need_tool"):
        max_steps = int(state.get("max_tool_steps") or 4)
        if int(state.get("tool_step") or 0) >= max_steps:
            return "generate_answer"
        return "execute_tool"
    return "generate_answer"


def route_after_execute_tool(state: RAGState) -> str:
    """工具执行后：还能继续决策则回到 decide_tool，否则生成回答。"""
    max_steps = int(state.get("max_tool_steps") or 4)
    step = int(state.get("tool_step") or 0)
    # 需要用户确认 / 缺槽位 / 达到上限 → 直接生成
    if state.get("requires_confirmation"):
        return "generate_answer"
    if state.get("missing_slots"):
        return "generate_answer"
    if step >= max_steps:
        return "generate_answer"
    return "decide_tool"
