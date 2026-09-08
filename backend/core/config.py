"""
全局配置，从环境变量读取。
其他模块 from core.config import settings 即可取用。
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # JWT
    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480          # 8 小时

    # 数据库
    database_url: str = "postgresql+asyncpg://workpilot:workpilot@localhost:5432/workpilot"

    # LLM 提供商选择：ollama | openai_compatible
    llm_provider: str = "ollama"

    # Ollama 配置
    ollama_base_url: str = "http://ollama:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_chat_model: str = "qwen2.5:7b"

    # OpenAI 兼容 API 配置（DeepSeek、Qwen-Max、vLLM 等）
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    openai_model: str = "deepseek-chat"

    # 文件存储
    upload_dir: str = "/data/uploads"
    max_file_size_mb: int = 200

    # 登录失败锁定阈值（默认值，以 system_config 表中的配置为准）
    login_max_fail_count: int = 5

    # 日志配置
    log_level: str = "DEBUG"
    log_rotation: str = "1 day"
    log_retention: str = "7 days"
    log_console: bool = True
    log_dir: str = "logs"

    # 运行环境
    environment: str = "development"

    # 密码策略
    password_min_length: int = 8

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
