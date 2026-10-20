"""对 ready 文档重新跑 pipeline（重建 chunk/embedding/tsv）。"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select, text  # noqa: E402
from db.session import async_session_factory  # noqa: E402
from services.document_pipeline import run_pipeline  # noqa: E402


async def main() -> None:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                text("SELECT id, file_name FROM documents WHERE status = 'ready' ORDER BY id")
            )
        ).all()
    print(f"待重建 {len(rows)} 份文档")
    for doc_id, fname in rows:
        print(f"  reindex {doc_id} {fname} ...")
        await run_pipeline(doc_id)
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
