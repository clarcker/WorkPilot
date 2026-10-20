"""PII 脱敏：正则替换为占位符。

仅在调用外部 LLM 出口处使用；本地 Ollama 不出网无需脱敏。
数据库与审计始终存原文。
"""
from __future__ import annotations

import re

# 顺序敏感：长模式（JWT、银行卡）放在短模式（手机号）之前，避免误截断
PII_RULES: list[tuple[str, str]] = [
    # ── 令牌 / 密钥 ────────────────────────────────────
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "[JWT令牌]"),
    (r"sk-[A-Za-z0-9]{20,}", "[API密钥]"),
    (r"gh[pors]_[A-Za-z0-9]{36,}", "[GitHub令牌]"),
    (r"AKID[A-Za-z0-9]{13,}", "[云服务密钥]"),
    (
        r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|private[_-]?key)\s*[:=]\s*[\"']?[A-Za-z0-9_\-\.]{8,}[\"']?",
        "[密钥配置]",
    ),
    (r"(?i)(password|passwd)\s*[:=]\s*[\"']?\S{4,}[\"']?", "[密码配置]"),

    # ── 个人身份信息 ────────────────────────────────────
    (r"\d{17}[\dXx]",         "[身份证]"),
    (r"\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}([- ]?\d{1,3})?", "[银行卡]"),
    (r"1[3-9]\d{9}",          "[手机号]"),
    (r"[\w.+-]+@[\w-]+\.\w+", "[邮箱]"),
]

_COMPILED = [(re.compile(p), label) for p, label in PII_RULES]

# 工具参数中若出现这些占位符，视为无效（LLM 把脱敏结果回传）
PLACEHOLDER_PATTERN = re.compile(
    r"\[(JWT令牌|API密钥|GitHub令牌|云服务密钥|密钥配置|密码配置|身份证|银行卡|手机号|邮箱)\]"
)


def anonymize_text(text: str) -> str:
    """对单段文本应用 PII 替换。"""
    if not text:
        return text
    out = text
    for cre, label in _COMPILED:
        out = cre.sub(label, out)
    return out


def anonymize_messages(messages: list[dict]) -> list[dict]:
    """脱敏 OpenAI 风格 messages 列表，不修改原 list。"""
    result: list[dict] = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            result.append({**m, "content": anonymize_text(content)})
        else:
            result.append(dict(m))
    return result


def contains_placeholder(value: str) -> bool:
    """工具参数是否含脱敏占位符（应视为缺失/无效）。"""
    return bool(value and PLACEHOLDER_PATTERN.search(value))
