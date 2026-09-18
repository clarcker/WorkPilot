"""用当前 fts 分词器重刷全部 doc_chunks.content_tsv。"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text  # noqa: E402
from db.session import async_session_factory  # noqa: E402
from services.fts import tokenize_for_search  # noqa: E402


async def main() -> None:
    async with async_session_factory() as db:
        rows = (await db.execute(text("SELECT id, content FROM doc_chunks"))).all()
        n = 0
        for cid, content in rows:
            tok = tokenize_for_search(content or "")
            await db.execute(
                text(
                    "UPDATE doc_chunks SET content_tsv = to_tsvector('simple', :tok) "
                    "WHERE id = :i"
                ),
                {"tok": tok, "i": cid},
            )
            n += 1
        await db.commit()
        print(f"re-tokenized {n} chunks")


if __name__ == "__main__":
    asyncio.run(main())
