"""Q1 文档生命周期 + Q2 多轮工具决策 单元测试。"""
from __future__ import annotations

import pytest

from graph.nodes import (
    _guess_time_scope,
    _normalize_args,
    _same_as_session_call,
    _build_sources,
    _build_tool_section,
)
from services.retriever import build_lifecycle_clause


class TestLifecycleClause:
    def test_employee_current_only_effective(self):
        assert build_lifecycle_clause("employee", "current") == "d.lifecycle = 'effective'"

    def test_employee_historical_includes_superseded(self):
        clause = build_lifecycle_clause("employee", "historical")
        assert "superseded" in clause
        assert "draft" not in clause

    def test_admin_current_includes_draft(self):
        clause = build_lifecycle_clause("dept_admin", "current")
        assert "draft" in clause
        assert "superseded" not in clause

    def test_admin_historical_all(self):
        clause = build_lifecycle_clause("super_admin", "historical")
        assert "effective" in clause and "superseded" in clause and "draft" in clause

    def test_default_scope_current(self):
        assert build_lifecycle_clause("employee") == "d.lifecycle = 'effective'"


class TestTimeScopeGuess:
    @pytest.mark.parametrize("q", [
        "旧版差旅办法里一类城市住宿是多少？",
        "2024 版住宿上限是多少？",
        "以前加班规定怎么算？",
        "修订前的报销标准",
        "员工手册2023版",
        "历史归档的加班规定",
    ])
    def test_historical_keywords(self, q):
        assert _guess_time_scope(q) == "historical"

    @pytest.mark.parametrize("q", [
        "现在出差住宿标准是多少？",
        "一线城市住宿报销上限是多少？",
        "病假医疗期最长能请多久？",
        "会议室怎么预约？",
    ])
    def test_current_default(self, q):
        assert _guess_time_scope(q) == "current"


class TestSameAsSessionCall:
    def test_same_query_args_reuse(self):
        calls = [{
            "tool_name": "query_reimbursement_limit",
            "tool_args": {},
            "tool_result": {"ok": True},
            "success": True,
        }]
        assert _same_as_session_call("query_reimbursement_limit", {}, calls) is True

    def test_different_tool_not_reuse(self):
        calls = [{
            "tool_name": "query_my_tickets",
            "tool_args": {},
            "tool_result": {},
            "success": True,
        }]
        assert _same_as_session_call("query_reimbursement_limit", {}, calls) is False

    def test_submit_draft_subset_reuse(self):
        calls = [{
            "tool_name": "submit_reimbursement_request",
            "tool_args": {"category": "差旅住宿", "amount": 2000, "days": 4},
            "tool_result": {"request_no": "RB-1", "status": "draft"},
            "success": True,
        }]
        assert _same_as_session_call(
            "submit_reimbursement_request",
            {"category": "差旅住宿", "amount": 2000},
            calls,
        ) is True

    def test_failed_call_not_reuse(self):
        calls = [{
            "tool_name": "query_reimbursement_limit",
            "tool_args": {},
            "tool_result": None,
            "success": False,
        }]
        assert _same_as_session_call("query_reimbursement_limit", {}, calls) is False

    def test_normalize_args_skips_empty(self):
        assert _normalize_args({"a": 1, "b": None, "c": ""}) == {"a": "1"}


class TestSourcesLifecycle:
    def test_sources_include_lifecycle_note(self):
        sources = _build_sources([{
            "chunk_id": 1,
            "doc_id": 2,
            "doc_name": "差旅报销管理办法-2024旧版.md",
            "content": "一类城市 400",
            "heading": "住宿",
            "page_no": None,
            "score": 0.8,
            "lifecycle": "superseded",
            "effective_date": "2024-01-01",
            "lifecycle_note": "已被 报销管理制度.md 替代（历史版本）",
        }])
        assert sources[0]["lifecycle"] == "superseded"
        assert "替代" in sources[0]["lifecycle_note"]


class TestToolSectionFromSession:
    def test_reuses_session_result_when_no_tool_this_turn(self):
        state = {
            "session_tool_calls": [{
                "tool_name": "query_reimbursement_limit",
                "tool_result": {"remaining": 16000},
                "success": True,
            }],
        }
        section = _build_tool_section(state)
        assert "query_reimbursement_limit" in section
        assert "16000" in section
