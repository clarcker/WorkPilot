"""seed eval/cases.json → eval_cases 表。"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

from eval.runner import seed_eval_cases_from_json  # noqa: E402


async def main() -> None:
    n = await seed_eval_cases_from_json()
    print(f"seeded eval_cases: {n}")


if __name__ == "__main__":
    asyncio.run(main())
