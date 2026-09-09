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
#  1. 脱敏节点
# ══════════════════════════════════════════════

# PII 替换规则：(regex, 替换标签)
# 顺序敏感：长模式（JWT、银行卡）放在短模式（手机号）之前，避免误截断
_PII_RULES: list[tuple[str, str]] = [
    # ── 令牌 / 密钥 ────────────────────────────────────
    # JWT（三段 base64url，点分隔）
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "[JWT令牌]"),
    # OpenAI / Anthropic 风格 sk- 密钥
    (r"sk-[A-Za-z0-9]{20,}", "[API密钥]"),
    # GitHub 个人/Actions 令牌
    (r"gh[pors]_[A-Za-z0-9]{36,}", "[GitHub令牌]"),
    # 阿里云 / 腾讯云 AccessKeyId
    (r"AKID[A-Za-z0-9]{13,}", "[云服务密钥]"),
    # 配置行：api_key=xxx  secret_key: xxx  access_token=xxx
    (r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|private[_-]?key)\s*[:=]\s*[\"']?[A-Za-z0-9_\-\.]{8,}[\"']?",
     "[密钥配置]"),
    # 配置行：password=xxx  passwd: xxx
    (r"(?i)(password|passwd)\s*[:=]\s*[\"']?\S{4,}[\"']?", "[密码配置]"),

    # ── 个人身份信息 ────────────────────────────────────
    # 身份证（18位，含X结尾）放在手机号之前避免前缀被截断
    (r"\d{17}[\dXx]",         "[身份证]"),
    # 银行卡（16-19位，可含空格或连字符）
    (r"\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}([- ]?\d{1,3})?", "[银行卡]"),
    # 手机号（大陆 1[3-9]xxxxxxxxx）
    (r"1[3-9]\d{9}",          "[手机号]"),
    # 邮箱
    (r"[\w.+-]+@[\w-]+\.\w+", "[邮箱]"),
]


async def anonymize_node(state: RAGState) -> dict:
    """将查询中的 PII / 密钥替换为占位符，再传给 LLM。"""
    text = state["query"]
    for pattern, label in _PII_RULES:
        text = re.sub(pattern, label, text)
    return {"anonymized_query": text}


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


async def classify_intent_node(state: RAGState) -> dict:
    """
    仅分析当前这一轮 query，判断 rag / chitchat。

    策略：
      1. 正则快速匹配明显闲聊（无 LLM 调用）
      2. 其余情况用 LLM 单轮分类（不传历史，保持低延迟）
      3. LLM 失败时降级为关键词匹配
    """
    query = state["query"]   # 并行执行，此时 anonymized_query 未必已写入，直接用原始 query

    if _is_obvious_chitchat(query):
        logger.debug(f"[classify_intent] regex→chitchat | {query[:50]!r}")
        return {"intent": "chitchat"}

    messages = [
        {
            "role": "system",
            "content": (
                "判断用户输入的类型，只回复一个词：\n"
                "- 纯粹的日常闲聊、问候、寒暄、与公司无关的话题 → chitchat\n"
                "- 涉及公司制度、流程、政策、文档，或需要办理某项业务 → rag\n"
                "  （包括但不限于：报销、请假、考勤、年假、薪资、福利、入职、"
                "离职、转正、培训、出差、IT/设备/网络、报修、工单、"
                "安全、合规、权限申请）\n"
                "只要问题与公司内部事务相关，一律回 rag。"
            ),
        },
        {"role": "user", "content": query},
    ]
    try:
        answer = await chat_complete(messages, temperature=0, max_tokens=5)
        intent = "rag" if "rag" in answer.lower() else "chitchat"
    except Exception as exc:
        logger.warning(f"[classify_intent] LLM失败，降级关键词匹配: {describe_exc(exc)}")
        intent = _classify_by_keywords(query)

    logger.debug(f"[classify_intent] {intent} | {query[:50]!r}")
    return {"intent": intent}


# ══════════════════════════════════════════════
#  3. 汇聚节点（fan-in 同步点）
# ══════════════════════════════════════════════

async def sync_node(state: RAGState) -> dict:
    """等待 anonymize 和 classify_intent 均完成后的汇聚点，不修改状态。"""
    return {}


# ══════════════════════════════════════════════
#  4. 检索节点
# ══════════════════════════════════════════════

async def retrieve_docs_node(state: RAGState) -> dict:
    """
    用脱敏后的 query 向量化，执行权限过滤的 pgvector 相似度搜索。
    检索完成后立即通过 SSE 推送 sources 给前端（无需等到生成完成）。
    """
    query = state["anonymized_query"] or state["query"]
    queue = state.get("token_queue")

    try:
        query_vec = await get_embedding(query)
        chunks = await retrieve(
            query_embedding=query_vec,
            user_id=state["user_id"],
            user_dept_id=state["user_dept_id"],
            user_role=state["user_role"],
            top_k=5,
            min_score=0.3,
        )
        logger.debug(f"[retrieve_docs] 检索到 {len(chunks)} 个 chunk")
        chunk_dicts = [dict(c) for c in chunks]

        # 检索完成立即推送 sources，用户可提前看到引用来源
        if queue and chunk_dicts:
            sources = _build_sources(chunk_dicts)
            if sources:
                await queue.put({"type": "sources", "content": sources})

        return {"retrieved_chunks": chunk_dicts}
    except Exception as exc:
        logger.error(f"[retrieve_docs] 检索失败: {describe_exc(exc)}", exc_info=True)
        return {"retrieved_chunks": [], "error": f"检索失败: {describe_exc(exc)}"}


# ══════════════════════════════════════════════
#  5. RAG 回答生成节点
# ══════════════════════════════════════════════

_RAG_SYSTEM_PROMPT = """\
你是企业内部知识库助手 WorkPilot。根据下方参考资料回答员工问题。

规则：
- 只引用参考资料中的信息，不要编造内容
- 若参考资料中没有相关内容，直接如实说明，并建议员工换关键词重试或联系相关部门
- 回答简洁准确，使用 Markdown 格式

【参考资料】
{context}
"""


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

    context    = _build_context(chunks)
    system_msg = _RAG_SYSTEM_PROMPT.format(context=context)
    sources    = _build_sources(chunks)

    messages = [{"role": "system", "content": system_msg}]
    for h in history[-6:]:   # 最近 3 轮历史（6 条）
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": state["anonymized_query"] or state["query"]})

    max_tokens = state.get("gen_max_tokens") or 2048
    full_answer = ""
    try:
        async for token in chat_stream(messages, temperature=0.3, max_tokens=max_tokens):
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
        async for token in chat_stream(messages, temperature=0.7, max_tokens=150):
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

规则：
- 用户要求查询自己的具体数据（员工信息、报销额度）或要求办理业务（报修、提工单）时，才调用工具
- 只是询问制度/流程/规定（如"报销制度是什么"、"设备维修怎么申请"），不要调用工具
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

    tools_desc_parts = []
    for t in tool_registry.get_tools_for_prompt(state.get("user_role", "employee")):
        tools_desc_parts.append(_format_tool_for_prompt(t))

    if not tools_desc_parts:
        return {"need_tool": False}

    tools_desc = "\n".join(tools_desc_parts)
    messages = [
        {"role": "system", "content": _TOOL_DECISION_PROMPT.format(tools_desc=tools_desc)},
        {"role": "user", "content": state.get("anonymized_query") or state["query"]},
    ]

    try:
        answer = await chat_complete(messages, temperature=0, max_tokens=200)
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

    tool_name = state.get("tool_name")
    tool_args = state.get("tool_args", {})
    queue = state.get("token_queue")

    if not tool_name:
        return {"tool_result": None, "tool_success": None, "tool_error": None}

    ctx = ToolContext(user_id=state["user_id"], user_role=state.get("user_role", "employee"),
                     user_dept_id=state.get("user_dept_id"),
                     dry_run=bool(state.get("tool_dry_run")))

    start = time.time()
    result = await tool_registry.execute(tool_name, tool_args, ctx)
    latency_ms = int((time.time() - start) * 1000)

    if queue:
        await queue.put({"type": "tool_call", "content": {
            "tool_name": tool_name, "tool_args": tool_args,
            "allowed": result.deny_reason is None,
            "deny_reason": result.deny_reason,
            "result": result.data if result.success else None,
            "error": result.error, "latency_ms": latency_ms}})

    if result.success:
        return {"tool_result": result.data, "tool_success": True, "tool_error": None}

    reason = result.error or result.deny_reason
    logger.warning(f"[execute_tool] {tool_name} 执行失败: {reason} | args={tool_args}")
    return {"tool_result": None, "tool_success": False, "tool_error": reason,
            "error": reason, "permission_denied": result.deny_reason}


def route_after_decide_tool(state: RAGState) -> str:
    if state.get("need_tool"):
        return "execute_tool"
    return "generate_answer"
