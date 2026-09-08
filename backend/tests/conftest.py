"""
全局测试配置与 Fixtures

包含：
- 异步事件循环
- 测试数据库引擎和会话
- 认证用户和 Token
- Mock 服务
"""

import sys
import pytest
import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

# Windows 上 asyncpg 与 ProactorEventLoop 不兼容，强制切换为 SelectorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 优先加载 .env.test
_env_test = Path(__file__).parent.parent / ".env.test"
if _env_test.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_test, override=True)

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from db.base import Base
from db.models import User, Department
from main import app
from core.security import hash_password, create_access_token
from services.document_parser import TextSegment


# ==================== 数据库配置 ====================

_raw_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/workpilot")
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    _raw_url.rsplit("/", 1)[0] + "/workpilot_test"
    if _raw_url.endswith("/workpilot")
    else _raw_url.rsplit("/", 1)[0] + "/workpilot_test"
)


def _parse_db_url(url: str) -> dict:
    """从 SQLAlchemy URL 解析 asyncpg 连接参数"""
    import re
    m = re.match(
        r"postgresql(?:\+asyncpg)?://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)",
        url,
    )
    if not m:
        raise ValueError(f"无法解析数据库 URL：{url}")
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": int(m.group(4) or 5432),
        "database": m.group(5),
    }


@pytest.fixture(scope="session", autouse=True)
def setup_test_database(request):
    """创建测试数据库并初始化表"""
    # 检查是否所有测试都标记了 no_db
    # 如果是，则跳过数据库设置
    all_no_db = all(
        item.get_closest_marker("no_db") 
        for item in request.session.items
    )
    if all_no_db:
        yield
        return

    async def _setup():
        params = _parse_db_url(TEST_DATABASE_URL)
        db_name = params["database"]

        conn = await asyncpg.connect(
            user=params["user"],
            password=params["password"],
            host=params["host"],
            port=params["port"],
            database="postgres",
            ssl=False,
        )
        db_exists = await conn.fetchval(
            f"SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname = '{db_name}')"
        )
        if not db_exists:
            await conn.execute(f"CREATE DATABASE {db_name}")
        await conn.close()

        engine = create_async_engine(
            TEST_DATABASE_URL, echo=False,
            connect_args={"ssl": False},
        )
        async with engine.begin() as c:
            await c.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def _teardown():
        engine = create_async_engine(
            TEST_DATABASE_URL, echo=False,
            connect_args={"ssl": False},
        )
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    try:
        asyncio.run(_setup())
    except Exception as e:
        raise RuntimeError(f"Test database setup failed: {e}") from e

    yield

    try:
        asyncio.run(_teardown())
    except Exception as e:
        print(f"[WARN] Test DB teardown failed: {e}")


@pytest.fixture
async def db_session(setup_test_database) -> AsyncGenerator[AsyncSession, None]:
    """为每个测试函数创建独立的数据库会话"""
    engine = create_async_engine(
        TEST_DATABASE_URL, echo=False,
        connect_args={"ssl": False},
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def cleanup_tables(setup_test_database):
    """每个测试结束后清理数据"""
    yield
    try:
        from db.session import engine as _app_engine
        await _app_engine.dispose()
    except Exception:
        pass

    engine = create_async_engine(
        TEST_DATABASE_URL, echo=False,
        connect_args={"ssl": False},
    )
    try:
        table_names = ", ".join(Base.metadata.tables.keys())
        async with engine.begin() as conn:
            await conn.execute(text(
                f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"
            ))
    except Exception as e:
        print(f"[WARN] cleanup_tables TRUNCATE failed: {e}")
    finally:
        await engine.dispose()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient（同步）"""
    from fastapi.testclient import TestClient
    from db.session import get_db

    def override_get_db():
        return db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
async def async_client():
    """异步 HTTP 客户端"""
    from httpx import AsyncClient, ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=True,
    ) as client:
        yield client


# ==================== 部门 Fixtures ====================

@pytest.fixture
async def tech_department(db_session: AsyncSession) -> Department:
    """创建技术部"""
    dept = Department(dept_code="RD", dept_name="技术部")
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


@pytest.fixture
async def hr_department(db_session: AsyncSession) -> Department:
    """创建人力资源部"""
    dept = Department(dept_code="HR", dept_name="人力资源部")
    db_session.add(dept)
    await db_session.commit()
    await db_session.refresh(dept)
    return dept


@pytest.fixture
async def multiple_departments(db_session, tech_department, hr_department):
    """获取多个部门"""
    return [tech_department, hr_department]


# ==================== 用户 Fixtures ====================

@pytest.fixture
async def super_admin_user(db_session: AsyncSession) -> User:
    """创建超级管理员用户"""
    user = User(
        username="admin",
        password_hash=hash_password("Admin@123"),
        real_name="超级管理员",
        display_name="超级管理员",
        employee_no="ADMIN001",
        role="super_admin",
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def dept_admin_user(db_session: AsyncSession, tech_department: Department) -> User:
    """创建部门管理员"""
    user = User(
        username="deptadmin",
        password_hash=hash_password("Admin@123"),
        real_name="部门管理员",
        display_name="部门管理员",
        employee_no="RD001",
        role="dept_admin",
        dept_id=tech_department.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def employee_user(db_session: AsyncSession, tech_department: Department) -> User:
    """创建普通员工"""
    user = User(
        username="employee",
        password_hash=hash_password("Employee@123"),
        real_name="员工",
        display_name="员工",
        employee_no="RD002",
        role="employee",
        dept_id=tech_department.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def multiple_employees(db_session: AsyncSession, tech_department: Department):
    """创建多个员工"""
    employees = []
    for i in range(3):
        user = User(
            username=f"emp{i}",
            password_hash=hash_password("Employee@123"),
            real_name=f"员工{i}",
            display_name=f"员工{i}",
            employee_no=f"RD{100+i}",
            role="employee",
            dept_id=tech_department.id,
            is_active=True,
            must_change_password=False,
        )
        db_session.add(user)
        employees.append(user)

    await db_session.commit()
    for emp in employees:
        await db_session.refresh(emp)

    return employees


# ==================== 认证 Fixtures ====================

@pytest.fixture
def super_admin_token(super_admin_user: User) -> str:
    """生成超级管理员 JWT Token"""
    token, jti, expires_at = create_access_token(
        user_id=super_admin_user.id,
        role=super_admin_user.role,
    )
    return token


@pytest.fixture
def dept_admin_token(dept_admin_user: User) -> str:
    """生成部门管理员 JWT Token"""
    token, jti, expires_at = create_access_token(
        user_id=dept_admin_user.id,
        role=dept_admin_user.role,
    )
    return token


@pytest.fixture
def employee_token(employee_user: User) -> str:
    """生成员工 JWT Token"""
    token, jti, expires_at = create_access_token(
        user_id=employee_user.id,
        role=employee_user.role,
    )
    return token


@pytest.fixture
def create_test_token():
    """工厂函数：创建任意用户的 Token"""
    def _create_token(user_id: int, role: str = "employee") -> str:
        token, jti, expires_at = create_access_token(user_id=user_id, role=role)
        return token
    return _create_token


# ==================== Mock Fixtures ====================

@pytest.fixture
def mock_ollama_embed(mocker):
    """Mock Ollama 嵌入服务"""
    return mocker.patch(
        "services.embedder.get_embedding",
        new_callable=AsyncMock,
        return_value=[0.1] * 768,
    )


@pytest.fixture
def mock_ollama_chat(mocker):
    """Mock Ollama 聊天服务"""
    return mocker.patch(
        "services.retriever.retrieve",
        new_callable=AsyncMock,
        return_value=[],
    )


@pytest.fixture
def mock_file_storage(mocker, tmp_path):
    """Mock 文件存储 - 让 aiofiles.open 写入临时目录"""
    import aiofiles

    original_open = aiofiles.open

    def mock_open(path, mode="r", **kwargs):
        # 将路径重定向到临时目录
        p = Path(path)
        new_path = tmp_path / p.name
        return original_open(new_path, mode=mode, **kwargs)

    return mocker.patch("aiofiles.open", side_effect=mock_open)


@pytest.fixture
def mock_pdf_parser(mocker):
    """Mock PDF 解析"""
    return mocker.patch(
        "services.document_parser.parse_document",
        new_callable=MagicMock,
        return_value=[
            TextSegment(page_no=1, heading=None, content="这是 PDF 的第一页内容。"),
        ],
    )


@pytest.fixture
def mock_docx_parser(mocker):
    """Mock DOCX 解析"""
    return mocker.patch(
        "services.document_parser.parse_document",
        new_callable=MagicMock,
        return_value=[
            TextSegment(page_no=None, heading="标题一", content="段落一内容"),
        ],
    )


# ==================== 标记和钩子 ====================

def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line("markers", "high_priority: 高优先级测试用例")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "e2e: 端到端测试")
    config.addinivalue_line("markers", "slow: 耗时测试")
    config.addinivalue_line("markers", "unit: 单元测试")
