"""配置加载：config.yaml 扁平 key + .env 敏感项 + 环境变量覆盖。"""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.no_db
class TestYamlConfig:
    def test_yaml_provides_non_sensitive_defaults(self):
        from core.config import get_settings

        s = get_settings()
        # 来自 config.yaml 的普通配置（具体值以当前 yaml 为准，这里断言字段已加载）
        assert s.llm_provider in ("ollama", "openai_compatible")
        assert s.ollama_chat_model  # 非空
        assert s.tool_timeout > 0
        assert s.rate_limit_login_per_minute > 0
        assert s.jwt_expire_minutes > 0
        assert s.log_dir

    def test_hot_reload_picks_up_yaml_change(self, tmp_path, monkeypatch):
        """改 config.yaml 后 maybe_reload_settings 应原地更新全局 settings。"""
        import os
        import time

        from pathlib import Path

        import core.config as config_mod

        yaml_path = config_mod._YAML_PATH
        original = yaml_path.read_text(encoding="utf-8")

        try:
            # 写入一个可识别的 tool_timeout
            text = original
            if "tool_timeout:" in text:
                import re

                text = re.sub(r"tool_timeout:\s*[\d.]+", "tool_timeout: 33.0", text)
            else:
                text = original + "\ntool_timeout: 33.0\n"
            yaml_path.write_text(text, encoding="utf-8")
            # 确保 mtime 变化（Windows 精度）
            os.utime(yaml_path, (time.time() + 2, time.time() + 2))

            assert config_mod.maybe_reload_settings() is True
            assert config_mod.settings.tool_timeout == 33.0
            # 二次调用无变更应返回 False
            assert config_mod.maybe_reload_settings() is False
        finally:
            yaml_path.write_text(original, encoding="utf-8")
            os.utime(yaml_path, (time.time() + 2, time.time() + 2))
            config_mod.maybe_reload_settings()

    def test_yaml_file_is_flat_and_matches_field_names(self):
        """防止再写成嵌套结构导致 flatten 后字段名对不上。"""
        from pathlib import Path

        import yaml

        path = Path(__file__).resolve().parents[2] / "config.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key, value in data.items():
            assert not isinstance(value, dict), (
                f"config.yaml 键 {key!r} 不应嵌套；扁平 key 才能与 Settings 字段对齐"
            )

    def test_cors_origin_list_splits(self):
        from core.config import get_settings

        origins = get_settings().cors_origin_list
        assert "http://localhost:5173" in origins
        assert all(not o.endswith("/") or o.count("/") <= 2 for o in origins)

    def test_validate_for_startup_flags_weak_secret(self, monkeypatch):
        from core.config import Settings

        s = Settings(
            jwt_secret_key="short",
            environment="production",
            cors_origins="*",
            _env_file=None,
        )
        warnings = s.validate_for_startup()
        assert any("JWT_SECRET_KEY" in w for w in warnings)
        assert any("CORS" in w for w in warnings)

    def test_env_overrides_yaml(self, monkeypatch):
        """环境变量优先级高于 yaml。"""
        monkeypatch.setenv("TOOL_TIMEOUT", "99")
        monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")

        import core.config as config_mod

        importlib.reload(config_mod)
        try:
            s = config_mod.Settings(_env_file=None)
            assert s.tool_timeout == 99.0
            assert s.llm_provider == "openai_compatible"
        finally:
            # 恢复，避免影响后续测试
            monkeypatch.delenv("TOOL_TIMEOUT", raising=False)
            monkeypatch.delenv("LLM_PROVIDER", raising=False)
            importlib.reload(config_mod)
