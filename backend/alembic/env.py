import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import pool

from alembic import context

# 加载环境变量
load_dotenv()

# Alembic Config 对象（读取 alembic.ini）
config = context.config

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入所有 model，autogenerate 需要 metadata
from db.base import Base
import db.models  # noqa: F401 — 确保所有 model 都注册到 metadata

target_metadata = Base.metadata

# 从环境变量读取数据库 URL（异步驱动）
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://workpilot:workpilot@localhost:5432/workpilot",
)


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本，不连接数据库"""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,       # 检测列类型变更
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """在线模式：连接真实数据库执行迁移"""
    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,  # migration 不需要连接池
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
