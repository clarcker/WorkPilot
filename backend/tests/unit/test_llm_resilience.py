"""P1/P4/P7 单元测试。"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from services.llm_resilience import (
    CircuitBreaker,
    CircuitState,
    LLMBusyError,
    call_with_resilience,
    get_breaker,
    is_retryable_exc,
    reset_circuits_for_tests,
)
from services.prompt_loader import load_prompts, prompt_set_version, prompts_dir
from tools.base import validate_tool_args


class TestRetryable:
    def test_timeout_retryable(self):
        assert is_retryable_exc(httpx.ConnectTimeout("t")) is True
        assert is_retryable_exc(httpx.ConnectError("c")) is True

    def test_value_error_not_retryable(self):
        assert is_retryable_exc(ValueError("bad json")) is False


class TestCircuitBreaker:
    def setup_method(self):
        reset_circuits_for_tests()
        from core.config import settings
        settings.llm_retry_max = 1
        settings.llm_retry_base_delay = 0.01
        settings.llm_circuit_fail_threshold = 5
        settings.llm_circuit_open_seconds = 30
        settings.llm_fallback_enabled = True
        settings.llm_max_concurrency_local = 8
        settings.llm_max_concurrency_external = 8
        settings.llm_queue_timeout = 5

    @pytest.mark.asyncio
    async def test_retry_then_open_then_fallback(self):
        async def factory(prov: str):
            if prov == "openai_compatible":
                raise httpx.HTTPStatusError(
                    "500", request=httpx.Request("POST", "http://x"),
                    response=httpx.Response(500, request=httpx.Request("POST", "http://x")),
                )
            return f"ok-from-{prov}"

        # llm_retry_max=1 → 每次 call 计 1 次失败
        for _ in range(5):
            with pytest.raises(Exception):
                await call_with_resilience("openai_compatible", factory, allow_fallback=False)
        b = get_breaker("openai_compatible")
        assert b.state == CircuitState.open
        result, meta = await call_with_resilience(
            "openai_compatible", factory, allow_fallback=True
        )
        assert result == "ok-from-ollama"
        assert meta["fallback_provider"] == "ollama"


class TestConcurrencyQueued:
    def setup_method(self):
        reset_circuits_for_tests()
        from core.config import settings
        settings.llm_max_concurrency_local = 2
        settings.llm_max_concurrency_external = 2
        settings.llm_queue_timeout = 0.25
        settings.llm_retry_max = 1
        settings.llm_retry_base_delay = 0.01

    @pytest.mark.asyncio
    async def test_third_request_busy_or_queued(self):
        queue: asyncio.Queue = asyncio.Queue()
        started = asyncio.Event()
        release = asyncio.Event()
        held = 0

        async def factory(prov: str):
            nonlocal held
            held += 1
            if held <= 2:
                started.set()
                await release.wait()
            return "ok"

        async def one():
            try:
                r, _ = await call_with_resilience("ollama", factory, queue=queue)
                return r
            except LLMBusyError:
                return "busy"

        tasks = [asyncio.create_task(one()) for _ in range(4)]
        await asyncio.wait_for(started.wait(), timeout=2)
        # 给后续请求时间去排队/超时
        await asyncio.sleep(0.4)
        release.set()
        results = await asyncio.gather(*tasks)
        assert "busy" in results or "ok" in results
        got_queued = False
        while not queue.empty():
            ev = queue.get_nowait()
            if isinstance(ev, dict) and ev.get("type") == "queued":
                got_queued = True
        assert got_queued or "busy" in results


class TestPromptLoader:
    def test_loads_all_files(self):
        prompts = load_prompts()
        for name in ("rag_system.md", "query_understand.md", "tool_decision.md",
                     "chitchat.md", "judge.md"):
            assert name in prompts and prompts[name].strip()

    def test_set_version_stable(self):
        v1 = prompt_set_version()
        v2 = prompt_set_version()
        assert v1 == v2 and len(v1) == 8

    def test_missing_file_raises(self, tmp_path, monkeypatch):
        from services import prompt_loader as pl
        monkeypatch.setattr(pl.settings, "prompts_dir", str(tmp_path))
        pl._load_all_cached.cache_clear()
        with pytest.raises(FileNotFoundError):
            pl.load_prompts()
        pl._load_all_cached.cache_clear()


class TestChatStreamNoRetryAfterFirstToken:
    def setup_method(self):
        reset_circuits_for_tests()
        from core.config import settings
        settings.llm_provider = "ollama"
        settings.llm_fallback_enabled = False
        settings.llm_retry_max = 3
        settings.llm_retry_base_delay = 0.01
        settings.llm_max_concurrency_local = 4
        settings.llm_queue_timeout = 5

    @pytest.mark.asyncio
    async def test_midstream_timeout_not_retried(self, monkeypatch):
        """第 5 个 token 后 ReadTimeout：不得重新流前 5 个 token，异常上抛。"""
        import services.llm_client as lc

        calls = {"n": 0}
        yielded: list[str] = []

        async def fake_stream(provider, messages, temperature, max_tokens):
            calls["n"] += 1
            for i in range(5):
                yield f"t{i}"
            raise httpx.ReadTimeout("mid-stream")

        monkeypatch.setattr(lc, "_stream_once", fake_stream)
        monkeypatch.setattr(lc, "resolve_provider", lambda role=None: "ollama")

        got_exc = None
        with pytest.raises(httpx.ReadTimeout):
            async for tok in lc.chat_stream([{"role": "user", "content": "hi"}]):
                yielded.append(tok)
        assert yielded == ["t0", "t1", "t2", "t3", "t4"]
        assert calls["n"] == 1  # 不重试、不 fallback


class TestDailyReportNumbers:
    def test_reject_fabricated_number(self):
        from services.daily_report import summary_numbers_allowed, _structured_bullets
        data = {
            "qa_total": 5, "qa_down": 2,
            "pending_reimb": 3, "pending_reimb_over_48h": 0,
            "pending_tickets": 1, "pending_tickets_over_48h": 0,
            "gaps": [{"query": "x", "count": 2}],
            "eval_run_id": 13, "eval_doc_hit": 0.844, "eval_mrr": 0.669,
            "eval_alert": None,
        }
        bullets = _structured_bullets("研发部", data)
        assert summary_numbers_allowed("昨日问答 5 条，待审批 3", data, bullets=bullets) is True
        # pending 3 写成 12：12 不在 bullets → 拒绝
        assert summary_numbers_allowed("昨日问答 5 条，待审批 12", data, bullets=bullets) is False
        assert summary_numbers_allowed("昨日问答 99 条", data, bullets=bullets) is False


class TestToolSchemaValidate:
    def test_enum_reject(self):
        schema = {
            "type": "object",
            "properties": {"category": {"type": "string", "enum": ["A", "B"]}},
            "required": ["category"],
        }
        ok, err = validate_tool_args(schema, {"category": "Z"})
        assert ok is False and "enum" in err or "允许" in err

    def test_integer_type(self):
        schema = {
            "type": "object",
            "properties": {"amount": {"type": "integer"}},
            "required": ["amount"],
        }
        ok, _ = validate_tool_args(schema, {"amount": "abc"})
        assert ok is False
        ok2, _ = validate_tool_args(schema, {"amount": "100"})
        assert ok2 is True
