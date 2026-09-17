"""中文分词 + tsvector 辅助（R3 关键词检索）。"""
from __future__ import annotations

import re

import jieba


def tokenize_for_search(text: str) -> str:
    """分词后空格拼接，供 to_tsvector('simple', ...) 写入。"""
    if not text:
        return ""
    # 去掉多余空白，保留中文/英文/数字
    cleaned = re.sub(r"\s+", " ", text).strip()
    tokens = [t for t in jieba.lcut_for_search(cleaned) if t.strip()]
    return " ".join(tokens)


def build_tsquery(text: str, max_terms: int = 20) -> str:
    """查询分词 → 'a | b | c' 形式的 tsquery。"""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    terms = []
    for t in jieba.lcut_for_search(cleaned):
        t = t.strip()
        if not t or len(t) < 1:
            continue
        # tsquery 特殊字符转义：去掉引号和反斜杠
        t = t.replace("'", "").replace("\\", "").replace('"', "")
        if t:
            terms.append(t)
        if len(terms) >= max_terms:
            break
    if not terms:
        return ""
    return " | ".join(terms)
