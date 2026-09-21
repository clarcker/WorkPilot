"""P4：prompt 文件加载与版本哈希。"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from core.config import settings
from core.logger import logger

_BACKEND = Path(__file__).resolve().parents[1]

PROMPT_FILES = (
    "rag_system.md",
    "query_understand.md",
    "tool_decision.md",
    "chitchat.md",
    "judge.md",
)


def prompts_dir() -> Path:
    d = Path(settings.prompts_dir)
    if not d.is_absolute():
        d = _BACKEND / d
    return d


def _file_version(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


@lru_cache(maxsize=1)
def _load_all_cached(root: str, mtime_sig: str) -> dict[str, str]:
    root_path = Path(root)
    out: dict[str, str] = {}
    for name in PROMPT_FILES:
        path = root_path / name
        if not path.exists():
            raise FileNotFoundError(f"prompt 文件缺失: {path}")
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"prompt 文件为空: {path}")
        out[name] = text
    return out


def _mtime_sig() -> str:
    d = prompts_dir()
    parts = []
    for name in PROMPT_FILES:
        p = d / name
        if p.exists():
            parts.append(f"{name}:{p.stat().st_mtime_ns}")
    return "|".join(parts)


def load_prompts() -> dict[str, str]:
    """加载全部 prompt；文件缺失/为空时抛错（启动即失败）。支持热加载（按 mtime）。"""
    d = prompts_dir()
    if not d.exists():
        raise FileNotFoundError(f"prompts 目录不存在: {d}")
    prompts = _load_all_cached(str(d), _mtime_sig())
    return dict(prompts)


def prompt_versions() -> dict[str, str]:
    prompts = load_prompts()
    return {name: _file_version(text) for name, text in prompts.items()}


def prompt_set_version() -> str:
    """所有 prompt 版本拼接后再 hash，便于一眼对比。"""
    vers = prompt_versions()
    raw = "|".join(f"{k}:{vers[k]}" for k in sorted(vers))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def get_prompt(name: str) -> str:
    prompts = load_prompts()
    if name not in prompts:
        raise KeyError(f"未知 prompt: {name}")
    return prompts[name]


def current_prompt_set() -> str:
    try:
        return prompt_set_version()
    except Exception as exc:
        logger.warning(f"[prompts] 版本计算失败: {exc}")
        return "unknown"
