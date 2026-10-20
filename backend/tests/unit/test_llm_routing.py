"""模型分档：resolve_provider / should_anonymize_for_llm / llm_query_for_completion。"""
from __future__ import annotations

import pytest

from core.config import settings


@pytest.fixture
def restore_settings():
    """保存并恢复 settings 可变字段。"""
    saved = {
        "llm_provider": settings.llm_provider,
        "admin_use_external_llm": settings.admin_use_external_llm,
        "openai_api_key": settings.openai_api_key,
    }
    yield
    settings.llm_provider = saved["llm_provider"]
    settings.admin_use_external_llm = saved["admin_use_external_llm"]
    settings.openai_api_key = saved["openai_api_key"]


@pytest.mark.no_db
class TestResolveProvider:
    def test_default_employee_uses_local(self, restore_settings):
        from services.llm_client import resolve_provider

        settings.llm_provider = "ollama"
        settings.admin_use_external_llm = False
        settings.openai_api_key = ""
        assert resolve_provider("employee") == "ollama"
        assert resolve_provider(None) == "ollama"

    def test_admin_external_requires_all_three(self, restore_settings):
        from services.llm_client import resolve_provider

        settings.llm_provider = "ollama"
        settings.admin_use_external_llm = True
        settings.openai_api_key = ""

        # 缺 API Key → 仍本地
        assert resolve_provider("super_admin") == "ollama"

        settings.openai_api_key = "sk-test"
        assert resolve_provider("super_admin") == "openai_compatible"
        assert resolve_provider("dept_admin") == "openai_compatible"
        # 员工不受管理员开关影响
        assert resolve_provider("employee") == "ollama"

    def test_global_openai_provider_applies_to_all(self, restore_settings):
        from services.llm_client import resolve_provider

        settings.llm_provider = "openai_compatible"
        settings.admin_use_external_llm = False
        settings.openai_api_key = "sk-test"
        assert resolve_provider("employee") == "openai_compatible"
        assert resolve_provider("super_admin") == "openai_compatible"


@pytest.mark.no_db
class TestShouldAnonymize:
    def test_local_does_not_anonymize(self, restore_settings):
        from services.llm_client import should_anonymize_for_llm

        settings.llm_provider = "ollama"
        settings.admin_use_external_llm = False
        settings.openai_api_key = ""
        assert should_anonymize_for_llm("employee") is False
        assert should_anonymize_for_llm("super_admin") is False

    def test_external_anonymizes(self, restore_settings):
        from services.llm_client import should_anonymize_for_llm

        settings.llm_provider = "openai_compatible"
        assert should_anonymize_for_llm("employee") is True

    def test_admin_external_route_anonymizes_admin_only(self, restore_settings):
        from services.llm_client import should_anonymize_for_llm

        settings.llm_provider = "ollama"
        settings.admin_use_external_llm = True
        settings.openai_api_key = "sk-test"
        assert should_anonymize_for_llm("super_admin") is True
        assert should_anonymize_for_llm("employee") is False


@pytest.mark.no_db
class TestLlmQueryForCompletion:
    def test_always_returns_original_query(self, restore_settings):
        """R0 后脱敏在 llm_client 出口；节点层始终送原文。"""
        from graph.nodes import llm_query_for_completion

        settings.llm_provider = "ollama"
        settings.admin_use_external_llm = False
        settings.openai_api_key = ""
        state = {
            "query": "张三的报销额度",
            "anonymized_query": "[姓名]的报销额度",
            "user_role": "employee",
        }
        assert llm_query_for_completion(state) == "张三的报销额度"

        settings.llm_provider = "openai_compatible"
        assert llm_query_for_completion(state) == "张三的报销额度"


@pytest.mark.no_db
class TestBuildToolSection:
    def test_no_tool_returns_empty(self):
        from graph.nodes import _build_tool_section

        assert _build_tool_section({"tool_name": None}) == ""
        assert _build_tool_section({}) == ""

    def test_success_includes_result_json(self):
        from graph.nodes import _build_tool_section

        section = _build_tool_section(
            {
                "tool_name": "query_reimbursement_limit",
                "tool_success": True,
                "tool_result": {"remaining": 37700, "category": "差旅住宿"},
                "tool_error": None,
            }
        )
        assert "query_reimbursement_limit" in section
        assert "37700" in section
        assert "差旅住宿" in section

    def test_failure_includes_error_reason(self):
        from graph.nodes import _build_tool_section

        section = _build_tool_section(
            {
                "tool_name": "create_it_ticket",
                "tool_success": False,
                "tool_result": None,
                "tool_error": "Tool 'create_it_ticket' timed out after 15.0s",
            }
        )
        assert "create_it_ticket" in section
        assert "timed out" in section
        assert "不要编造" in section

    def test_permission_denied_uses_deny_reason(self):
        from graph.nodes import _build_tool_section

        section = _build_tool_section(
            {
                "tool_name": "query_employee_profile",
                "tool_success": False,
                "tool_result": None,
                "tool_error": None,
                "permission_denied": "普通员工只能查询自己的信息",
            }
        )
        assert "普通员工只能查询自己的信息" in section
