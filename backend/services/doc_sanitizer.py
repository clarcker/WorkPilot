"""文档内容消毒：降低提示注入对生成节点的影响。

原则：不删除业务信息，只把「对 AI 的指令」类片段中性化，
并在生成 system prompt 中声明资料不可信指令。
"""
from __future__ import annotations

import re

# 常见注入指令模式（中英）
_INJECT_PATTERNS = [
    re.compile(r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts?)"),
    re.compile(r"(?i)disregard\s+(?:the\s+)?(?:system|previous)\s+prompt"),
    re.compile(r"(?i)you\s+must\s+(?:now\s+)?(?:obey|follow)\s+(?:the\s+)?(?:following\s+)?instructions"),
    re.compile(r"(?i)system\s*prompt\s*[:：]"),
    re.compile(r"(?i)override\s+(?:safety|policy|instructions)"),
    re.compile(r"忽略(?:以上|之前|上述)?(?:所有)?(?:指令|提示|规则)"),
    re.compile(r"无视(?:系统|安全)?提示"),
    # 不再匹配宽泛的「你现在是」——会误伤「转正后你现在是正式员工」
    re.compile(r"你现在是(?:AI|助手|模型|管理员|system)"),
    re.compile(r"不要遵守.{0,8}(?:规则|指令|限制)"),
    re.compile(r"把(?:之前|上述)的要求放一边"),
    re.compile(r"【?系统指令】?"),
    re.compile(r"<\|im_start\|>|<\|im_end\|>|###\s*system\s*[:：]?", re.I),
]


def sanitize_doc_content(text: str) -> str:
    """中和文档中的提示注入指令片段。"""
    if not text:
        return text
    out = text
    for pat in _INJECT_PATTERNS:
        out = pat.sub("[已过滤：文档内疑似指令]", out)
    return out


def contains_injection(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in _INJECT_PATTERNS)
