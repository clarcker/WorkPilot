"""R0 单元测试：脱敏只在外部 provider 出口生效。"""
from __future__ import annotations

import pytest

from core.anonymizer import anonymize_messages, anonymize_text, contains_placeholder


@pytest.mark.no_db
class TestAnonymizer:
    def test_phone_masked(self):
        assert "13800138000" not in anonymize_text("我的手机是13800138000")
        assert "[手机号]" in anonymize_text("我的手机是13800138000")

    def test_email_masked(self):
        out = anonymize_text("联系 a.b@company.com 谢谢")
        assert "a.b@company.com" not in out
        assert "[邮箱]" in out

    def test_messages_all_masked(self):
        msgs = [
            {"role": "user", "content": "打我电话13800138000"},
            {"role": "assistant", "content": "邮箱 x@y.com"},
            {"role": "system", "content": "password=Secret123"},
        ]
        out = anonymize_messages(msgs)
        joined = " ".join(m["content"] for m in out)
        assert "13800138000" not in joined
        assert "x@y.com" not in joined
        assert "Secret123" not in joined

    def test_placeholder_detect(self):
        assert contains_placeholder("phone is [手机号]")
        assert not contains_placeholder("phone is 13800138000")


@pytest.mark.no_db
class TestLlmExitAnonymize:
    @pytest.mark.asyncio
    async def test_external_masks_history_and_query(self, monkeypatch):
        import services.llm_client as lc
        from core.config import settings

        settings.llm_provider = "openai_compatible"
        settings.openai_api_key = "sk-test"
        settings.admin_use_external_llm = False

        captured: dict = {}

        async def fake_openai(messages, temperature, max_tokens):
            captured["messages"] = messages
            return "ok"

        monkeypatch.setattr(lc, "_openai_complete", fake_openai)

        msgs = [
            {"role": "system", "content": "资料：用户手机13800138000"},
            {"role": "user", "content": "查一下 a@b.com 的信息"},
        ]
        await lc.chat_complete(msgs, user_role="employee")
        joined = " ".join(m["content"] for m in captured["messages"])
        assert "13800138000" not in joined
        assert "a@b.com" not in joined

    @pytest.mark.asyncio
    async def test_local_keeps_original(self, monkeypatch):
        import services.llm_client as lc
        from core.config import settings

        settings.llm_provider = "ollama"
        settings.admin_use_external_llm = False
        settings.openai_api_key = ""

        captured: dict = {}

        async def fake_ollama(messages, temperature, max_tokens):
            captured["messages"] = messages
            return "ok"

        monkeypatch.setattr(lc, "_ollama_complete", fake_ollama)
        msgs = [{"role": "user", "content": "手机13800138000"}]
        await lc.chat_complete(msgs, user_role="employee")
        assert "13800138000" in captured["messages"][0]["content"]
