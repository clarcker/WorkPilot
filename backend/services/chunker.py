"""
文本分块服务。

将 TextSegment 列表合并为固定大小的 Chunk，并带有重叠（overlap）以保留上下文。

算法：
  1. 按顺序合并 segments，直到当前 chunk 达到 chunk_chars
  2. 记录第一个 segment 的 page_no / heading 作为 chunk 的元数据
  3. 新 chunk 以上一个 chunk 末尾 overlap_chars 个字符作为前缀（软重叠）
  4. 若单个 segment 超过 chunk_chars，则强制按字符切割

默认参数（适配 nomic-embed-text，最大 8192 token，中文 ~1 char ≈ 1.5 token）：
  chunk_chars  = 800   → ≈ 600~1200 token，远低于上限
  overlap_chars = 80   → ≈ 8% 重叠
"""
from __future__ import annotations

from typing import TypedDict

from core.logger import logger
from services.document_parser import TextSegment


class ChunkData(TypedDict):
    content:     str
    chunk_index: int
    page_no:     int | None
    heading:     str | None


def chunk_segments(
    segments:      list[TextSegment],
    chunk_chars:   int = 800,
    overlap_chars: int = 80,
) -> list[ChunkData]:
    """
    将 TextSegment 列表分割为 ChunkData 列表。

    Args:
        segments:      document_parser 解析结果
        chunk_chars:   每块最大字符数
        overlap_chars: 与前一块共享的尾部字符数（软重叠）

    Returns:
        ChunkData 列表，chunk_index 从 0 开始。
    """
    if not segments:
        return []

    logger.info("Chunking started | segments={count} | chunk_chars={chars}", count=len(segments), chars=chunk_chars)

    chunks: list[ChunkData] = []
    overlap_tail = ""          # 上一个 chunk 末尾用于重叠的文本
    current_text = ""
    current_page_no: int | None = None
    current_heading: str | None = None

    def _flush(text: str, page_no: int | None, heading: str | None) -> None:
        nonlocal overlap_tail
        text = text.strip()
        if not text:
            return
        chunks.append(
            ChunkData(
                content=text,
                chunk_index=len(chunks),
                page_no=page_no,
                heading=heading,
            )
        )
        # 保留末尾作为下一块的重叠前缀
        overlap_tail = text[-overlap_chars:] if overlap_chars > 0 else ""

    for seg in segments:
        seg_text = seg["text"].strip()
        if not seg_text:
            continue

        # 若加上这段会超出 chunk_chars，先 flush 当前内容
        candidate = (overlap_tail + "\n\n" + current_text + "\n\n" + seg_text).strip() if current_text else (overlap_tail + "\n\n" + seg_text).strip() if overlap_tail else seg_text

        if len(candidate) > chunk_chars and current_text:
            # flush 当前 chunk（不含本段）
            _flush(
                (overlap_tail + "\n\n" + current_text).strip() if overlap_tail else current_text,
                current_page_no,
                current_heading,
            )
            current_text = ""
            current_page_no = None
            current_heading = None

        # 如果单段本身就超过 chunk_chars，强制按字符切割
        if len(seg_text) > chunk_chars:
            start = 0
            first = True
            while start < len(seg_text):
                piece = seg_text[start: start + chunk_chars]
                prefix = overlap_tail if first and overlap_tail else ""
                full_piece = (prefix + "\n\n" + piece).strip() if prefix else piece
                _flush(full_piece, seg["page_no"], seg["heading"])
                start += chunk_chars - overlap_chars
                first = False
            overlap_tail_candidate = seg_text[-overlap_chars:]
            overlap_tail = overlap_tail_candidate
            current_text = ""
            current_page_no = None
            current_heading = None
            continue

        # 追加到当前 chunk
        if current_text:
            current_text += "\n\n" + seg_text
        else:
            current_text = seg_text
            current_page_no = seg["page_no"]
            current_heading = seg["heading"]

    # flush 最后剩余内容
    if current_text:
        _flush(
            (overlap_tail + "\n\n" + current_text).strip() if overlap_tail else current_text,
            current_page_no,
            current_heading,
        )

    logger.info("Chunking finished | chunks={count}", count=len(chunks))

    return chunks
