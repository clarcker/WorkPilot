# WorkPilot v2 后端测试框架指南

**文档版本：** 1.0  
**编制日期：** 2026-06-01

本文档提供后端测试的实现指南，包括框架选型、项目结构、Fixtures 设计、Mock 策略等。

---

## 一、技术栈选型

### 1.1 核心依赖

```toml
# backend/pyproject.toml 中需要添加的测试依赖

[project.optional-dependencies]
dev = [
    "pytest==7.4.0",                    # 测试框架
    "pytest-asyncio==0.21.0",          # 异步测试支持
    "pytest-cov==4.1.0",               # 覆盖率检测
    "pytest-mock==3.11.1",             # Mock 库
    "pytest-env==0.8.2",               # 环境变量管理
    "httpx==0.24.0",                   # 异步 HTTP 客户端
    "factory-boy==3.2.1",              # 对象工厂（生成测试数据）
    "faker==18.0.0",                   # 随机数据生成
]
```

### 1.2 为什么选择这些工具

| 工具 | 理由 |
|---|---|
| **pytest** | 功能完整，与 FastAPI 兼容性好，支持异步、Fixtures、参数化 |
| **pytest-asyncio** | FastAPI 是异步框架，需要异步测试支持 |
| **pytest-cov** | 生成覆盖率报告，集成到 CI/CD |
| **pytest-mock** | 提供 `mocker` fixture，简化 Mock 操作 |
| **httpx** | FastAPI TestClient 的推荐替代品，支持异步 |
| **factory-boy** | 声明式定义测试数据工厂，避免重复的 fixture 代码 |
| **faker** | 生成真实感的随机数据（用户名、邮箱、手机号等） |

---

## 二、项目结构

```
backend/
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # 全局 Fixtures（数据库、认证、Mock 等）
│   ├── factories/                    # 对象工厂
│   │   ├── __init__.py
│   │   ├── user_factory.py           # 用户工厂
│   │   ├── department_factory.py     # 部门工厂
│   │   ├── document_factory.py       # 文档工厂
│   │   └── conversation_factory.py   # 会话工厂
│   ├── fixtures/                     # 测试数据和文件
│   │   ├── sample.md
│   │   ├── sample.pdf
│   │   ├── sample.docx
│   │   ├── test_data.json
│   │   └── users.json
│   ├── unit/                         # 单元测试
│   │   ├── test_auth.py
│   │   ├── test_validators.py
│   │   ├── test_utils.py
│   │   └── test_models.py
│   ├── integration/                  # 集成测试
│   │   ├── test_auth_flow.py
│   │   ├── test_user_management.py
│   │   ├── test_document_pipeline.py
│   │   ├── test_chat_workflow.py
│   │   ├── test_audit_logs.py
│   │   └── test_permissions.py
│   ├── e2e/                          # 端到端测试
│   │   ├── test_full_workflow.py
│   │   └── test_performance.py
│   └── utils/                        # 测试工具函数
│       ├── __init__.py
│       ├── auth_helpers.py           # 生成 Token、登录等
│       ├── db_helpers.py             # 数据库清理、创建测试数据
│       └── api_helpers.py            # 常用 API 调用包装
├── pytest.ini                        # pytest 配置
├── .env.test                         # 测试环境变量
└── pyproject.toml                    # 项目配置
```

---

## 三、pytest 配置

### 3.1 pytest.ini

```ini
[pytest]
# 基础配置
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# 日志配置
log_cli = true
log_cli_level = INFO
log_cli_format = %(asctime)s [%(levelname)s] %(message)s
log_file = logs/pytest.log
log_file_level = DEBUG

# 异步配置
asyncio_mode = auto

# 覆盖率配置
addopts = 
    --cov=app 
    --cov-report=html:htmlcov 
    --cov-report=term-missing
    --cov-branch
    --cov-fail-under=75
    -v
    --tb=short

# 测试路径
testpaths = tests
```

### 3.2 .env.test

```env
# 测试环境变量
ENVIRONMENT=test
DEBUG=true

# 数据库（使用独立的测试库）
DATABASE_URL=postgresql://postgres:password@localhost/workpilot_test

# JWT
JWT_SECRET_KEY=test-secret-key-do-not-use-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=8

# Ollama（可选 Mock）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_CHAT_MODEL=qwen2.5:7b

# 外部 API（使用 Mock）
OPENAI_API_KEY=mock-key
DEEPSEEK_API_KEY=mock-key

# 功能开关
ENABLE_EXTERNAL_LLM=false
MOCK_OLLAMA=true

# 日志
LOG_LEVEL=DEBUG
```

---

## 四、全局 Fixtures（conftest.py）

### 4.1 数据库 Fixtures

```python
# tests/conftest.py

import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.database import Base, get_db
from app.main import app

# 测试数据库连接
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost/workpilot_test"

@pytest.fixture(scope="session")
def event_loop():
    """创建 session 级别的事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def async_engine():
    """创建异步引擎，session 级别（仅创建一次）"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,  # 连接前验证
    )
    
    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # 清理：删除所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()

@pytest.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """为每个测试函数创建独立的数据库会话"""
    async_session = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        # 开始事务
        await session.begin()
        yield session
        # 回滚（清理测试数据）
        await session.rollback()

@pytest.fixture
def client(app, db_session):
    """FastAPI TestClient"""
    def override_get_db():
        return db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    from fastapi.testclient import TestClient
    return TestClient(app)

@pytest.fixture
async def async_client(app, db_session):
    """异步 HTTP 客户端"""
    def override_get_db():
        return db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    from httpx import AsyncClient
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

### 4.2 认证 Fixtures

```python
# tests/conftest.py 续

from app.models import User
from app.utils.auth import create_access_token, hash_password
from tests.factories import UserFactory

@pytest.fixture
async def super_admin_user(db_session) -> User:
    """创建超级管理员用户"""
    user = await UserFactory.create(
        username="admin",
        role="super_admin",
        is_active=True,
    )
    await db_session.refresh(user)
    return user

@pytest.fixture
async def dept_admin_user(db_session, dept_department) -> User:
    """创建部门管理员"""
    user = await UserFactory.create(
        username="deptadmin",
        role="dept_admin",
        dept_id=dept_department.id,
        is_active=True,
    )
    await db_session.refresh(user)
    return user

@pytest.fixture
async def employee_user(db_session, dept_department) -> User:
    """创建普通员工"""
    user = await UserFactory.create(
        username="employee",
        role="employee",
        dept_id=dept_department.id,
        is_active=True,
    )
    await db_session.refresh(user)
    return user

@pytest.fixture
def super_admin_token(super_admin_user) -> str:
    """生成超级管理员 JWT Token"""
    return create_access_token(
        data={"sub": str(super_admin_user.id), "username": super_admin_user.username}
    )

@pytest.fixture
def dept_admin_token(dept_admin_user) -> str:
    """生成部门管理员 JWT Token"""
    return create_access_token(
        data={"sub": str(dept_admin_user.id), "username": dept_admin_user.username}
    )

@pytest.fixture
def employee_token(employee_user) -> str:
    """生成员工 JWT Token"""
    return create_access_token(
        data={"sub": str(employee_user.id), "username": employee_user.username}
    )

@pytest.fixture
async def authenticated_client(client, super_admin_token):
    """预先认证的测试客户端"""
    client.headers.update({"Authorization": f"Bearer {super_admin_token}"})
    return client
```

### 4.3 数据库数据 Fixtures

```python
# tests/conftest.py 续

from app.models import Department

@pytest.fixture
async def dept_department(db_session) -> Department:
    """创建测试部门"""
    from tests.factories import DepartmentFactory
    dept = await DepartmentFactory.create(
        dept_code="RD",
        dept_name="技术部",
    )
    await db_session.refresh(dept)
    return dept

@pytest.fixture
async def multiple_departments(db_session):
    """创建多个测试部门"""
    from tests.factories import DepartmentFactory
    depts = await asyncio.gather(
        DepartmentFactory.create(dept_code="HR", dept_name="人力资源部"),
        DepartmentFactory.create(dept_code="FIN", dept_name="财务部"),
        DepartmentFactory.create(dept_code="OPS", dept_name="运维部"),
    )
    for dept in depts:
        await db_session.refresh(dept)
    return depts
```

### 4.4 Mock Fixtures

```python
# tests/conftest.py 续

from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_ollama_embed(mocker):
    """Mock Ollama 嵌入服务"""
    return mocker.patch(
        "app.services.embedding.embed_text",
        new_callable=AsyncMock,
        return_value=[0.1, 0.2, 0.3, ...],  # 模拟 embedding 向量
    )

@pytest.fixture
def mock_openai_api(mocker):
    """Mock OpenAI API"""
    return mocker.patch(
        "app.services.llm.call_openai",
        new_callable=AsyncMock,
        return_value="模拟的 AI 回答",
    )

@pytest.fixture
def mock_file_upload(mocker):
    """Mock 文件上传"""
    return mocker.patch(
        "app.services.storage.save_file",
        new_callable=AsyncMock,
        return_value="/data/uploads/docs/1/uuid.pdf",
    )
```

---

## 五、对象工厂（Factory）设计

### 5.1 基础工厂类

```python
# tests/factories/__init__.py

from .user_factory import UserFactory
from .department_factory import DepartmentFactory
from .document_factory import DocumentFactory
from .conversation_factory import ConversationFactory

__all__ = [
    "UserFactory",
    "DepartmentFactory",
    "DocumentFactory",
    "ConversationFactory",
]
```

### 5.2 用户工厂示例

```python
# tests/factories/user_factory.py

import factory
from factory.asyncio import AsyncFactory
from faker import Faker
from app.models import User
from app.utils.auth import hash_password

fake = Faker("zh_CN")

class UserFactory(AsyncFactory):
    """用户数据工厂"""
    
    class Meta:
        model = User
        sqlalchemy_session_persistence = "flush"
    
    id = factory.Sequence(lambda n: n + 1)
    username = factory.LazyAttribute(lambda _: fake.user_name())
    password = factory.LazyFunction(lambda: hash_password("Password@123"))
    real_name = factory.LazyAttribute(lambda _: fake.name())
    display_name = factory.LazyAttribute(lambda _: fake.name())
    employee_no = factory.LazyAttribute(lambda _: f"RD{fake.random_int(min=1000, max=9999)}")
    email = factory.LazyAttribute(lambda _: fake.email())
    role = factory.LazyChoice(["employee", "dept_admin", "super_admin"])
    dept_id = None
    is_active = True
    failed_login_count = 0
    locked_at = None
    must_change_password = False
    last_login_at = None
    created_at = factory.Faker("date_time_this_month")
    updated_at = factory.Faker("date_time_this_month")

    @classmethod
    async def create_with_password(cls, **kwargs):
        """创建用户并设置特定密码"""
        kwargs["password"] = hash_password(kwargs.pop("password", "Password@123"))
        return await cls.create(**kwargs)
```

### 5.3 文档工厂示例

```python
# tests/factories/document_factory.py

import factory
from factory.asyncio import AsyncFactory
from app.models import Document

class DocumentFactory(AsyncFactory):
    """文档数据工厂"""
    
    class Meta:
        model = Document
    
    id = factory.Sequence(lambda n: n + 1)
    file_name = factory.Faker("file_name")
    file_uuid = factory.LazyAttribute(lambda _: str(factory.Faker("uuid4")))
    file_type = factory.LazyChoice(["pdf", "docx", "md"])
    file_size = factory.Faker("random_int", min=1000, max=1000000)
    dept_id = factory.SubFactory("tests.factories.DepartmentFactory")
    visibility = factory.LazyChoice(["global", "non_customer", "dept_only", "specific_users"])
    category = factory.LazyChoice(["行政制度", "技术文档", "流程规范"])
    version = "v1.0"
    status = factory.LazyChoice(["processing", "ready", "failed", "archived"])
    chunk_count = factory.Faker("random_int", min=5, max=50)
    error_message = None
    uploaded_by = factory.SubFactory("tests.factories.UserFactory", role="dept_admin")
    created_at = factory.Faker("date_time_this_month")
    updated_at = factory.Faker("date_time_this_month")
```

---

## 六、测试编写示例

### 6.1 单元测试示例

```python
# tests/unit/test_auth.py

import pytest
from app.utils.auth import hash_password, verify_password, create_access_token
from app.exceptions import InvalidCredentialsError

class TestPasswordHashing:
    """密码哈希测试"""
    
    def test_password_hashed_correctly(self):
        """验证密码正确哈希"""
        password = "SecurePassword@123"
        hashed = hash_password(password)
        
        assert hashed != password
        assert verify_password(password, hashed)
    
    def test_wrong_password_fails(self):
        """错误密码应验证失败"""
        password = "SecurePassword@123"
        hashed = hash_password(password)
        
        assert not verify_password("WrongPassword", hashed)
    
    @pytest.mark.parametrize("password", [
        "short",
        "no_uppercase1",
        "NO_LOWERCASE1",
        "NoSpecialChar1",
    ])
    def test_weak_password_validation(self, password):
        """弱密码应被拒绝"""
        with pytest.raises(ValueError):
            hash_password(password)

class TestJWTToken:
    """JWT Token 测试"""
    
    def test_token_creation(self):
        """验证 Token 创建"""
        data = {"sub": "user_id", "username": "testuser"}
        token = create_access_token(data)
        
        assert isinstance(token, str)
        assert token.count(".") == 2  # JWT 三段结构
    
    def test_token_expiration(self):
        """验证 Token 过期"""
        # 使用极短的过期时间创建 Token
        data = {"sub": "user_id"}
        token = create_access_token(data, expires_delta=0.001)
        
        import time
        time.sleep(0.01)
        
        # Token 应过期
        # 验证逻辑见集成测试
```

### 6.2 集成测试示例

```python
# tests/integration/test_auth_flow.py

import pytest
from httpx import AsyncClient

class TestLoginFlow:
    """登录流程集成测试"""
    
    @pytest.mark.asyncio
    async def test_login_success(self, async_client: AsyncClient, employee_user):
        """验证成功登录"""
        response = await async_client.post(
            "/api/auth/login",
            json={
                "username": employee_user.username,
                "password": "Password@123",  # 工厂默认密码
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "access_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
        assert data["data"]["user"]["username"] == employee_user.username
    
    @pytest.mark.asyncio
    async def test_login_wrong_password(self, async_client: AsyncClient, employee_user):
        """验证密码错误的登录拒绝"""
        response = await async_client.post(
            "/api/auth/login",
            json={
                "username": employee_user.username,
                "password": "WrongPassword",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 40001
        assert "access_token" not in data["data"]
    
    @pytest.mark.asyncio
    async def test_login_then_get_me(self, async_client: AsyncClient, employee_user):
        """验证登录后获取用户信息"""
        # 1. 登录
        login_resp = await async_client.post(
            "/api/auth/login",
            json={
                "username": employee_user.username,
                "password": "Password@123",
            },
        )
        token = login_resp.json()["data"]["access_token"]
        
        # 2. 使用 Token 调用 /me
        async_client.headers.update({"Authorization": f"Bearer {token}"})
        me_resp = await async_client.get("/api/auth/me")
        
        assert me_resp.status_code == 200
        assert me_resp.json()["data"]["username"] == employee_user.username
    
    @pytest.mark.asyncio
    async def test_consecutive_failed_logins_lock_account(
        self, async_client: AsyncClient, employee_user
    ):
        """验证连续 5 次失败登录后账号被锁定"""
        username = employee_user.username
        
        # 尝试 5 次错误登录
        for i in range(5):
            response = await async_client.post(
                "/api/auth/login",
                json={"username": username, "password": "WrongPassword"},
            )
            assert response.json()["code"] == 40001
        
        # 第 6 次尝试应返回账号已锁定
        response = await async_client.post(
            "/api/auth/login",
            json={"username": username, "password": "WrongPassword"},
        )
        assert response.json()["code"] == 40002
        assert "已锁定" in response.json()["message"]

class TestLogoutFlow:
    """登出流程测试"""
    
    @pytest.mark.asyncio
    async def test_logout_revokes_token(
        self, async_client: AsyncClient, employee_token
    ):
        """验证登出后 Token 被吊销"""
        async_client.headers.update({"Authorization": f"Bearer {employee_token}"})
        
        # 1. 登出
        logout_resp = await async_client.post("/api/auth/logout")
        assert logout_resp.status_code == 200
        
        # 2. 尝试使用同一 Token 调用 API，应失败
        me_resp = await async_client.get("/api/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["code"] == 40102
```

### 6.3 端到端测试示例

```python
# tests/e2e/test_full_workflow.py

import pytest
from httpx import AsyncClient
import json

class TestCompleteWorkflow:
    """完整工作流测试：登录 → 上传文档 → 对话"""
    
    @pytest.mark.asyncio
    async def test_login_upload_document_chat(
        self, async_client: AsyncClient, dept_admin_user, employee_user
    ):
        """完整的业务流程"""
        
        # 1. 部门管理员登录
        admin_login = await async_client.post(
            "/api/auth/login",
            json={"username": dept_admin_user.username, "password": "Password@123"},
        )
        admin_token = admin_login.json()["data"]["access_token"]
        
        # 2. 上传文档
        with open("tests/fixtures/sample.pdf", "rb") as f:
            upload_resp = await async_client.post(
                "/api/docs/upload",
                headers={"Authorization": f"Bearer {admin_token}"},
                files={"file": f},
                data={
                    "visibility": "global",
                    "category": "测试文档",
                    "version": "v1.0",
                },
            )
        assert upload_resp.status_code == 200
        doc_id = upload_resp.json()["data"]["id"]
        
        # 3. 员工登录
        emp_login = await async_client.post(
            "/api/auth/login",
            json={"username": employee_user.username, "password": "Password@123"},
        )
        emp_token = emp_login.json()["data"]["access_token"]
        
        # 4. 员工发起对话（SSE）
        async with AsyncClient(app=app, base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/api/chat/stream",
                headers={"Authorization": f"Bearer {emp_token}"},
                json={"message": "文档中讲了什么？"},
            ) as resp:
                assert resp.status_code == 200
                
                # 验证 SSE 流
                event_types = set()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        event = json.loads(line[6:])
                        event_types.add(event.get("type"))
                
                # 应该包含这些事件类型
                assert "conversation_id" in event_types
                assert "token" in event_types
                assert "done" in event_types
```

---

## 七、测试执行

### 7.1 本地运行

```bash
# 安装测试依赖
cd backend
uv sync

# 配置测试环境
export $(cat .env.test | xargs)

# 创建测试数据库
createdb workpilot_test

# 运行所有测试
pytest

# 运行特定模块的测试
pytest tests/integration/test_auth_flow.py -v

# 运行特定测试用例
pytest tests/integration/test_auth_flow.py::TestLoginFlow::test_login_success -v

# 生成覆盖率报告
pytest --cov=app --cov-report=html

# 查看覆盖率
open htmlcov/index.html

# 运行测试并输出详细信息
pytest -v -s --tb=short

# 只运行高优先级测试（标记）
pytest -m "high_priority" -v

# 忽略某些测试
pytest --ignore=tests/e2e/ -v
```

### 7.2 CI/CD 集成

```yaml
# .github/workflows/backend-test.yml

name: Backend Tests

on:
  push:
    branches: [main, develop]
    paths:
      - 'backend/**'
  pull_request:
    branches: [main, develop]
    paths:
      - 'backend/**'

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: pgvector/pgvector:0.4.1-pg14
        env:
          POSTGRES_PASSWORD: password
          POSTGRES_DB: workpilot_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v3
      
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Install dependencies
        run: cd backend && uv sync
      
      - name: Run tests
        env:
          DATABASE_URL: postgresql://postgres:password@localhost/workpilot_test
        run: |
          cd backend
          pytest --cov=app --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./backend/coverage.xml
          flags: backend
          fail_ci_if_error: true
          verbose: true
```

---

## 八、测试标记（Markers）

```python
# tests/conftest.py 或 pytest.ini

import pytest

def pytest_configure(config):
    """定义自定义标记"""
    config.addinivalue_line(
        "markers", 
        "asyncio: mark test as async (deselect with '-m \"not asyncio\"')"
    )
    config.addinivalue_line(
        "markers",
        "high_priority: mark test as high priority (P0)"
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers",
        "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow running"
    )
```

### 使用标记

```python
@pytest.mark.high_priority
def test_critical_feature():
    pass

@pytest.mark.integration
def test_api_integration():
    pass

@pytest.mark.slow
@pytest.mark.asyncio
async def test_large_file_upload():
    pass

# 运行特定标记的测试
# pytest -m "high_priority" -v
# pytest -m "integration" -v
# pytest -m "not slow" -v
```

---

## 九、最佳实践

### 9.1 编写好的测试

| 原则 | 说明 | 示例 |
|---|---|---|
| **Single Responsibility** | 每个测试只测试一个功能 | ❌ test_login_and_chat<br>✅ test_login_success / test_login_wrong_password |
| **Arrange-Act-Assert** | 测试结构清晰 | 准备数据 → 执行操作 → 验证结果 |
| **Descriptive Names** | 测试名称说明意图 | ✅ test_login_with_disabled_account<br>❌ test_login_2 |
| **Use Fixtures** | 复用测试数据 | 使用工厂生成对象，而不是硬编码 |
| **Isolate External Dependencies** | Mock 外部依赖 | Mock Ollama、LLM API、文件存储 |
| **Avoid Test Interdependence** | 测试独立执行 | 每个测试自清理，不依赖执行顺序 |

### 9.2 避免常见陷阱

| 陷阱 | 问题 | 解决 |
|---|---|---|
| 测试顺序依赖 | 一个失败导致其他失败 | 使用数据库事务隔离，每个测试独立 |
| 全局状态污染 | Mock 不清理 | 使用 Fixture 的 yield，自动清理 |
| 测试太慢 | 超时或等待外部服务 | Mock 外部服务，使用内存数据库 |
| 覆盖率陷阱 | 100% 覆盖但仍有 Bug | 关注边界情况、错误路径、并发场景 |
| Flaky 测试 | 偶尔失败 | 避免 sleep，使用轮询或事件驱动 |

### 9.3 性能测试

```python
# tests/e2e/test_performance.py

import pytest
from locust import HttpUser, task, between

class ChatUser(HttpUser):
    """并发对话用户模拟"""
    
    wait_time = between(1, 3)
    
    @task
    def stream_chat(self):
        """并发对话请求"""
        with self.client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "报销规范是什么？"},
            headers={"Authorization": f"Bearer {self.token}"},
        ) as resp:
            assert resp.status_code == 200

# 运行：locust -f tests/e2e/test_performance.py
```

---

## 附录：快速命令

```bash
# 开发时快速运行
pytest tests/ -v -s                    # 详细输出，不捕获 print

# 仅运行失败的测试
pytest --lf                             # last failed

# 运行最近修改的测试
pytest --ff                             # failed first

# 生成覆盖率报告
pytest --cov=app --cov-report=html -v

# 并行运行（使用 pytest-xdist）
pytest -n auto                          # 自动并行数

# 调试单个测试
pytest tests/integration/test_auth.py::TestLoginFlow::test_login_success -vvs --pdb

# 清理 pytest 缓存
pytest --cache-clear
```

---

## 参考资源

- [pytest 官方文档](https://docs.pytest.org/)
- [FastAPI 测试文档](https://fastapi.tiangolo.com/deployment/testing/)
- [SQLAlchemy 异步文档](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Factory Boy 文档](https://factoryboy.readthedocs.io/)
