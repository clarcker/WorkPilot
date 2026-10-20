"""中文分词 + tsvector 辅助（R3 关键词检索）。"""
from __future__ import annotations

import re

import jieba

# 停用词：几乎每份制度文档都出现，进 tsquery 会稀释专有词权重
_STOPWORDS = {
    "的", "了", "是", "什么", "怎么", "如何", "哪些", "吗", "呢", "啊",
    "公司", "员工", "可以", "需要", "应该", "进行", "相关", "以及",
    "？", "?", "。", "，", ",", "、", "：", ":", "；", ";",
}


def tokenize_for_search(text: str) -> str:
    """分词后空格拼接，供 to_tsvector('simple', ...) 写入。"""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    tokens = [
        t for t in jieba.lcut_for_search(cleaned)
        if t.strip() and t not in _STOPWORDS and len(t.strip()) >= 1
    ]
    return " ".join(tokens)


def build_tsquery(text: str, max_terms: int = 20) -> str:
    """查询分词 → 'a | b | c' 形式的 tsquery，过滤停用词与过短 token。"""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    terms: list[str] = []
    seen: set[str] = set()
    for t in jieba.lcut_for_search(cleaned):
        t = t.strip()
        if not t or t in _STOPWORDS or t in seen:
            continue
        # 至少 2 字符的中英数，避免「的/了」
        if len(t) < 2 and not t.isdigit():
            continue
        t = t.replace("'", "").replace("\\", "").replace('"', "")
        if t and t not in seen:
            terms.append(t)
            seen.add(t)
        if len(terms) >= max_terms:
            break
    if not terms:
        return ""
    return " | ".join(terms)
