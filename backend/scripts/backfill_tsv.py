"""回填 doc_chunks.content_tsv（已有文档的关键词检索列）。

用法：cd backend && uv run python scripts/backfill_tsv.py
"""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from services.fts import tokenize_for_search  # noqa: E402


async def main() -> None:
    url = os.getenv("DATABASE_URL")
    engine = create_async_engine(url)
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with Session() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT id, content FROM doc_chunks "
                    "WHERE content_tsv IS NULL LIMIT 5000"
                )
            )
        ).all()
        print(f"待回填 {len(rows)} 条")
        n = 0
        for cid, content in rows:
            tok = tokenize_for_search(content or "")
            if not tok:
                continue
            await db.execute(
                text(
                    "UPDATE doc_chunks SET content_tsv = "
                    "to_tsvector('simple', :tok) WHERE id = :id"
                ),
                {"tok": tok, "id": cid},
            )
            n += 1
            if n % 100 == 0:
                await db.commit()
                print(f"  ... {n}")
        await db.commit()
        print(f"完成，回填 {n} 条")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
