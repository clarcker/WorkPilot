"""
初始化超级管理员密码

运行方式：
    cd backend
    uv run python scripts/seed_admin.py

说明：
    migration 中已插入超级管理员行，但密码为占位符。
    此脚本将密码更新为真实的 bcrypt hash。
    首次部署后执行一次即可；后续重置密码也可复用此脚本。
"""

import asyncio
import os
import sys
import bcrypt
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://workpilot:workpilot@localhost:5432/workpilot",
)

DEFAULT_PASSWORD = "Admin@123"


async def main():
    password = os.getenv("ADMIN_INIT_PASSWORD", DEFAULT_PASSWORD)

    # 生成 bcrypt hash
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    _PLACEHOLDER = "$2b$12$placeholder_run_seed_to_set_real_password"

    async with session_factory() as session:
        result = await session.execute(
            text("SELECT id, password_hash FROM users WHERE username = 'admin'")
        )
        row = result.fetchone()
        if row is None:
            print("[ERROR] 未找到 admin 用户，请先执行 alembic upgrade head")
            sys.exit(1)

        if row.password_hash != _PLACEHOLDER:
            print("[SKIP] 管理员密码已设置，跳过（如需重置请直接调用 reset-password 接口）")
            return

        await session.execute(
            text("""
                UPDATE users
                SET password_hash = :hash, must_change_password = TRUE
                WHERE username = 'admin'
            """),
            {"hash": hashed},
        )
        await session.commit()

    await engine.dispose()

    print("[OK] 超级管理员密码已设置")
    print("     用户名：admin")
    print(f"     初始密码：{password}")
    print("     首次登录将强制修改密码")


if __name__ == "__main__":
    asyncio.run(main())
