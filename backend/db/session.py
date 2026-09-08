from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://workpilot:workpilot@localhost:5432/workpilot")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,          # 生产环境关闭 SQL 日志，调试时改为 True
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # 自动检测断开的连接
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI Depends 注入用"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
