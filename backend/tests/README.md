# WorkPilot v2 后端测试指南

## 快速开始

### 1. 安装测试依赖

```bash
cd backend
uv sync
```

### 2. 配置测试环境

```bash
# 复制测试环境变量
cp .env.test .env

# 或者指定环境变量文件
export $(cat .env.test | xargs)
```

### 3. 创建测试数据库

```bash
# PostgreSQL 必须已运行
createdb workpilot_test
```

### 4. 运行测试

```bash
# 运行所有测试
pytest

# 运行特定模块
pytest tests/unit/test_auth.py -v
pytest tests/integration/test_auth_integration.py -v

# 运行特定测试用例
pytest tests/integration/test_auth_integration.py::TestLoginFlow::test_login_success -v

# 生成覆盖率报告
pytest --cov=app --cov-report=html

# 运行仅高优先级测试
pytest -m "high_priority" -v

# 运行且忽略 e2e 测试
pytest --ignore=tests/e2e/ -v

# 运行时显示 print 输出
pytest -v -s
```

## 测试文件组织

```
tests/
├── conftest.py                          # 全局 Fixtures
├── unit/                                # 单元测试
│   ├── test_auth.py                    # 密码、Token 等
│   └── __init__.py
├── integration/                         # 集成测试
│   ├── test_auth_integration.py        # 登录、登出、Token 刷新
│   ├── test_user_management.py         # 用户 CRUD、权限
│   ├── test_department_management.py   # 部门 CRUD
│   ├── test_document_management.py     # 文档上传、检索、权限
│   ├── test_chat.py                    # 对话、会话管理
│   ├── test_audit_and_config.py        # 审计日志、系统配置
│   └── __init__.py
├── e2e/                                 # 端到端测试
│   ├── test_complete_workflow.py       # 完整业务流程
│   └── __init__.py
├── utils/                               # 测试工具函数
│   ├── auth_helpers.py                 # Token 生成、过期 Token
│   ├── db_helpers.py                   # 用户、部门创建
│   └── __init__.py
└── README.md                            # 本文件
```

## 测试用例统计

| 模块 | 单元测试 | 集成测试 | E2E 测试 | 总计 |
|---|---|---|---|---|
| 认证（Auth） | 17 | 25 | 1 | 43 |
| 部门管理 | 0 | 17 | 1 | 18 |
| 用户管理 | 0 | 26 | 1 | 27 |
| 文档管理 | 0 | 20 | 1 | 21 |
| 对话聊天 | 0 | 16 | 1 | 17 |
| 审计日志与配置 | 0 | 18 | 1 | 19 |
| **总计** | **17** | **122** | **6** | **145** |

## 测试标记说明

### 优先级

```bash
# 运行高优先级测试（⭐⭐⭐）
pytest -m "high_priority" -v

# 运行所有非 slow 测试
pytest -m "not slow" -v
```

### 类别

```bash
# 仅运行单元测试
pytest -m "unit" -v

# 仅运行集成测试
pytest -m "integration" -v

# 仅运行端到端测试
pytest -m "e2e" -v
```

### 特殊标记

```bash
# 跳过耗时测试（用于快速反馈）
pytest -m "not slow" -v

# 仅运行异步测试
pytest -m "asyncio" -v
```

## 常见命令

```bash
# 快速测试（仅高优先级，忽略 e2e）
pytest -m "high_priority and not slow" -v

# 完整测试（包括覆盖率）
pytest --cov=app --cov-report=html -v

# 仅显示失败的测试
pytest --tb=short -v

# 运行最后失败的测试
pytest --lf

# 运行上次失败的测试首先
pytest --ff

# 调试单个测试
pytest tests/integration/test_auth_integration.py::TestLoginFlow::test_login_success -vvs --pdb

# 清理缓存
pytest --cache-clear
```

## Fixtures 说明

### 数据库 Fixtures

- `db_session`：为每个测试提供隔离的数据库会话
- `async_engine`：异步数据库引擎（session 作用域）

### 用户 Fixtures

- `super_admin_user`：超级管理员用户
- `dept_admin_user`：部门管理员用户
- `employee_user`：普通员工用户
- `multiple_employees`：多个员工用户

### Token Fixtures

- `super_admin_token`：超管 JWT Token
- `dept_admin_token`：部门管理员 Token
- `employee_token`：员工 Token
- `authenticated_client`：预先认证的同步客户端
- `authenticated_async_client`：预先认证的异步客户端

### 部门 Fixtures

- `tech_department`：技术部
- `hr_department`：人力资源部
- `multiple_departments`：多个部门

### Mock Fixtures

- `mock_ollama_embed`：Mock Ollama 嵌入服务
- `mock_ollama_chat`：Mock Ollama 聊天服务
- `mock_openai_api`：Mock OpenAI API
- `mock_file_storage`：Mock 文件存储
- `mock_pdf_parser`：Mock PDF 解析
- `mock_docx_parser`：Mock DOCX 解析

## 代码示例

### 基础测试

```python
@pytest.mark.asyncio
@pytest.mark.high_priority
async def test_login_success(
    async_client: AsyncClient,
    employee_user: User
):
    """测试成功登录"""
    response = await async_client.post(
        "/api/auth/login",
        json={
            "username": employee_user.username,
            "password": "Employee@123",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "access_token" in data["data"]
```

### 权限测试

```python
@pytest.mark.asyncio
@pytest.mark.high_priority
async def test_employee_cannot_create_user(
    async_client: AsyncClient,
    employee_token: str
):
    """测试员工无权创建用户"""
    async_client.headers.update({"Authorization": f"Bearer {employee_token}"})
    
    response = await async_client.post(
        "/api/admin/users",
        json={...},
    )
    
    assert response.json()["code"] == 40301
```

### 流式测试

```python
@pytest.mark.asyncio
async def test_stream_chat(
    async_client: AsyncClient,
    employee_token: str
):
    """测试流式对话"""
    async_client.headers.update({"Authorization": f"Bearer {employee_token}"})
    
    async with async_client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "测试"},
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            # 处理 SSE 事件
            pass
```

## CI/CD 集成

项目包含 `.github/workflows/backend-test.yml`，自动在 PR 和推送时运行测试。

## 覆盖率报告

生成覆盖率报告后，在浏览器中打开：

```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

## 调试技巧

### 查看详细日志

```bash
pytest -vv -s --log-cli-level=DEBUG
```

### 进入调试器

```bash
pytest --pdb
```

### 显示最慢的 10 个测试

```bash
pytest --durations=10
```

## 常见问题

### Q: 数据库连接失败

确保 PostgreSQL 正在运行且测试数据库存在：

```bash
psql -U postgres -c "CREATE DATABASE workpilot_test;"
```

### Q: Fixtures 作用域问题

- `session` 作用域的 Fixtures 在整个测试会话中共享
- `function` 作用域的 Fixtures 在每个测试函数中重新创建

### Q: Mock 未生效

确保 Mock 路径正确，例如：

```python
@pytest.fixture
def mock_service(mocker):
    # 重要：Mock 应该在模块被导入的地方
    return mocker.patch("app.services.module.function")
```

## 更多资源

- [pytest 官方文档](https://docs.pytest.org/)
- [AsyncIO 测试](https://docs.pytest.org/en/latest/how-to-use.html#asynchronous-vs-blocking-api)
- [FastAPI 测试](https://fastapi.tiangolo.com/advanced/async-tests/)
- [SQLAlchemy 异步测试](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
