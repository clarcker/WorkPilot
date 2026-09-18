"""
全局配置。

加载顺序（优先级从高到低）：
  1. 环境变量
  2. backend/.env          — 仅敏感信息（密钥/密码/含密码的连接串）
  3. backend/config.yaml   — 非敏感业务配置
  4. 代码内默认值

其他模块：from core.config import settings
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_YAML_PATH = _BACKEND_ROOT / "config.yaml"


def _load_yaml() -> dict[str, Any]:
    if not _YAML_PATH.exists():
        return {}
    raw = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8")) or {}
    return _flatten(raw)


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """把嵌套 yaml 展平成 Settings 字段名（llm.provider → llm_provider）。"""
    out: dict[str, Any] = {}
    for k, v in data.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, f"{key}_"))
        else:
            out[key] = v
    return out


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """把 config.yaml 作为字段默认值来源（优先级低于 env / .env）。"""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data = _load_yaml()

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        val = self._data.get(field_name)
        return val, field_name, False

    def __call__(self) -> dict[str, Any]:
        collected: dict[str, Any] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            value, _, _ = self.get_field_value(field, field_name)
            if value is not None:
                collected[field_name] = value
        return collected


class Settings(BaseSettings):
    # ── 敏感：仅 .env / 环境变量 ─────────────────────────────────
    jwt_secret_key: str = Field(default="", description="JWT 签名密钥，必须在 .env 配置")
    database_url: str = Field(
        default="postgresql+asyncpg://workpilot:workpilot@localhost:5432/workpilot",
        description="数据库连接串（含密码，放 .env）",
    )
    openai_api_key: str = Field(default="", description="外部 LLM API Key，放 .env")
    # 仅 seed_admin.py / compose 使用，不进 yaml
    admin_init_password: str = "Admin@123"

    # ── 非敏感：yaml 可配，env 可覆盖 ───────────────────────────
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    llm_provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_chat_model: str = "qwen2.5:7b"
    admin_use_external_llm: bool = False
    openai_base_url: str = "https://api.deepseek.com/v1"
    openai_model: str = "deepseek-chat"

    llm_connect_timeout: float = 10.0
    llm_complete_timeout: float = 120.0
    llm_stream_timeout: float = 300.0
    tool_timeout: float = 15.0

    # 检索（R2/R3 + E4 对照开关）
    retrieval_top_k: int = 5
    retrieval_min_score: float = 0.25
    retrieval_enable_fts: bool = True
    retrieval_must_include: bool = True
    retrieval_merge_chunks: bool = True
    retrieval_rrf_k: int = 60
    retrieval_w_vec: float = 0.7
    retrieval_w_kw: float = 0.3

    upload_dir: str = "/data/uploads"
    max_file_size_mb: int = 200
    login_max_fail_count: int = 5

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost"
    rate_limit_login_per_minute: int = 10
    rate_limit_chat_per_5min: int = 20

    log_level: str = "DEBUG"
    log_rotation: str = "1 day"
    log_retention: str = "7 days"
    log_console: bool = True
    log_dir: str = "logs"

    environment: str = "development"
    password_min_length: int = 8

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def validate_for_startup(self) -> list[str]:
        """启动时安全检查，返回警告列表。"""
        warnings: list[str] = []
        if (
            self.jwt_secret_key in ("", "change-me-to-a-long-random-string")
            or len(self.jwt_secret_key) < 32
        ):
            warnings.append(
                "JWT_SECRET_KEY 未设置或过短（建议 64+ 位随机串）："
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        if not self.is_dev and "*" in self.cors_origins:
            warnings.append("生产环境禁止 CORS 通配符 *，请配置 cors_origins 白名单")
        return warnings

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 优先级：init > env > .env > yaml > 默认值
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def _config_mtimes() -> tuple[float, float]:
    yaml_m = _YAML_PATH.stat().st_mtime if _YAML_PATH.exists() else 0.0
    env_path = _BACKEND_ROOT / ".env"
    env_m = env_path.stat().st_mtime if env_path.exists() else 0.0
    return yaml_m, env_m


# 记录启动时的文件 mtime；之后由 maybe_reload_settings 检测变更
_seen_mtimes = _config_mtimes()


def maybe_reload_settings() -> bool:
    """
    检测 config.yaml / .env 是否被修改，是则原地更新全局 settings。

    重要：多数模块是 `from core.config import settings`，拿到的是同一对象引用，
    所以必须 setattr 原地更新，不能只换全局变量。
    改完配置后无需重启进程（uvicorn 热重载默认不监视 yaml/.env）。
    """
    global _seen_mtimes
    now = _config_mtimes()
    if now == _seen_mtimes:
        return False

    get_settings.cache_clear()
    fresh = Settings()
    for name in Settings.model_fields:
        setattr(settings, name, getattr(fresh, name))
    _seen_mtimes = now
    return True


def describe_llm_routing() -> str:
    """启动/诊断用：当前分档路由一览。"""
    from services.llm_client import resolve_provider  # 延迟导入避免环

    emp = resolve_provider("employee")
    adm = resolve_provider("super_admin")
    key_ok = bool(settings.openai_api_key and settings.openai_api_key.strip())
    return (
        f"llm_provider={settings.llm_provider} "
        f"admin_use_external={settings.admin_use_external_llm} "
        f"api_key={'set' if key_ok else 'MISSING'} "
        f"employee→{emp} admin→{adm} "
        f"model={settings.openai_model if adm == 'openai_compatible' else settings.ollama_chat_model} "
        f"base={settings.openai_base_url if adm == 'openai_compatible' else settings.ollama_base_url}"
    )

