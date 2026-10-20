"""
LangGraph RAG + Tool Calling 工作流组装与编译。

  START ──► anonymize
              │
              ▼
         query_understand  (R1：intent + rewrite 一次调用)
              │
              ▼
           sync ──chitchat──► generate_chitchat ──► END
              │
              rag
              ▼
         retrieve_docs  (R3：向量+关键词 RRF，R4：分块合并)
              │
              ▼
         decide_tool ⇄ execute_tool
              │
              ▼
        generate_answer ──► END
"""
from langgraph.graph import END, START, StateGraph

from graph.nodes import (
    anonymize_node,
    query_understand_node,
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

_builder = StateGraph(RAGState)

_builder.add_node("anonymize",        anonymize_node)
_builder.add_node("query_understand", query_understand_node)
_builder.add_node("sync",             sync_node)
_builder.add_node("retrieve_docs",    retrieve_docs_node)
_builder.add_node("decide_tool",      decide_tool_node)
_builder.add_node("execute_tool",     execute_tool_node)
_builder.add_node("generate_answer",  generate_answer_node)
_builder.add_node("generate_chitchat", generate_chitchat_node)

# START → anonymize ∥ query_understand
_builder.add_edge(START, "anonymize")
_builder.add_edge(START, "query_understand")
_builder.add_edge("anonymize", "sync")
_builder.add_edge("query_understand", "sync")

_builder.add_conditional_edges(
    "sync",
    route_after_sync,
    {"rag": "retrieve_docs", "chitchat": "generate_chitchat"},
)

_builder.add_edge("retrieve_docs", "decide_tool")

_builder.add_conditional_edges(
    "decide_tool",
    route_after_decide_tool,
    {"execute_tool": "execute_tool", "generate_answer": "generate_answer"},
)

_builder.add_conditional_edges(
    "execute_tool",
    route_after_execute_tool,
    {"decide_tool": "decide_tool", "generate_answer": "generate_answer"},
)

_builder.add_edge("generate_answer", END)
_builder.add_edge("generate_chitchat", END)

rag_graph = _builder.compile()
