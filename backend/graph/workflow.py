"""
LangGraph RAG + Tool Calling 工作流组装与编译。

工作流图（含多步工具循环）：

  START ──┬──► anonymize ──────────────────┐
          └──► classify_intent ────────────┤
                                           ▼
                                         sync
                                           │
                              ┌─ chitchat ─┤
                              │            └─ rag ──► retrieve_docs ──► decide_tool
                              ▼                                              │
                    generate_chitchat                     ┌──────────────────┤
                              │                           ▼                  │
                              │                    execute_tool ──(循环)──► decide_tool
                              │                           │
                              │                           ▼
                              │                    generate_answer
                              │                           │
                              └───────────────────────► END
"""
from langgraph.graph import END, START, StateGraph

from graph.nodes import (
    anonymize_node,
    classify_intent_node,
    decide_tool_node,
    execute_tool_node,
    generate_answer_node,
    generate_chitchat_node,
    retrieve_docs_node,
    route_after_decide_tool,
    route_after_execute_tool,
    route_after_sync,
    sync_node,
)
from graph.state import RAGState

# ------------------------------------------------------------------
# 构建图
# ------------------------------------------------------------------
_builder = StateGraph(RAGState)

# 节点注册
_builder.add_node("anonymize",          anonymize_node)
_builder.add_node("classify_intent",    classify_intent_node)
_builder.add_node("sync",               sync_node)
_builder.add_node("retrieve_docs",      retrieve_docs_node)
_builder.add_node("decide_tool",        decide_tool_node)
_builder.add_node("execute_tool",       execute_tool_node)
_builder.add_node("generate_answer",    generate_answer_node)
_builder.add_node("generate_chitchat",  generate_chitchat_node)

# START → anonymize 和 classify_intent 并行
_builder.add_edge(START,             "anonymize")
_builder.add_edge(START,             "classify_intent")

# 两者均完成后汇聚到 sync
_builder.add_edge("anonymize",       "sync")
_builder.add_edge("classify_intent", "sync")

# sync 完成后按意图分支
_builder.add_conditional_edges(
    "sync",
    route_after_sync,
    {
        "rag":      "retrieve_docs",
        "chitchat": "generate_chitchat",
    },
)

# RAG 路径：检索 → 决定是否需要工具
_builder.add_edge("retrieve_docs",     "decide_tool")

# 工具决策后：需要工具 → 执行；不需要 → 生成回答
_builder.add_conditional_edges(
    "decide_tool",
    route_after_decide_tool,
    {
        "execute_tool":    "execute_tool",
        "generate_answer": "generate_answer",
    },
)

# 工具执行后：可循环回 decide_tool，或直接生成
_builder.add_conditional_edges(
    "execute_tool",
    route_after_execute_tool,
    {
        "decide_tool":     "decide_tool",
        "generate_answer": "generate_answer",
    },
)

_builder.add_edge("generate_answer",   END)

# 闲聊路径
_builder.add_edge("generate_chitchat", END)

# ------------------------------------------------------------------
# 编译
# ------------------------------------------------------------------
rag_graph = _builder.compile()
