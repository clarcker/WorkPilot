# WorkPilot v2 后端测试计划

**文档版本：** 1.0  
**编制日期：** 2026-06-01  
**覆盖范围：** FastAPI 后端全接口及工作流层

---

## 一、测试策略

### 1.1 测试分层

| 层级 | 覆盖范围 | 工具 | 预期覆盖率 |
|---|---|---|---|
| **单元测试** | 工具函数、数据验证、业务逻辑 | pytest | 80%+ |
| **集成测试** | API 路由 + 数据库交互 + LangGraph 工作流 | pytest + TestClient | 75%+ |
| **端到端测试** | 完整流程（登录 → 上传文档 → 提问 → SSE 输出） | pytest + httpx | 60%+ |
| **性能测试** | 并发、大文件、向量查询性能 | locust | 峰值 100 RPS |

### 1.2 测试环境

```
后端：FastAPI + Uvicorn（test 模式）
数据库：PostgreSQL（独立测试库，每个测试自动回滚）
Ollama：Mock（单元/集成测试），实际（端到端/性能测试）
认证：使用测试 JWT token
```

### 1.3 测试数据管理

- **Fixtures**：预置用户、部门、文档等基础数据
- **数据库隔离**：每个测试用事务隔离，自动清理
- **Mock 外部服务**：Ollama 嵌入、外部 LLM API 等

---

## 二、测试覆盖清单

### 2.1 按模块划分

| 模块 | 接口数 | 测试用例数 | 优先级 |
|---|---|---|---|
| 认证（Auth） | 6 | 18 | ⭐⭐⭐ |
| 部门管理 | 4 | 12 | ⭐⭐⭐ |
| 用户管理 | 10 | 32 | ⭐⭐⭐ |
| 文档管理 | 8 | 28 | ⭐⭐⭐ |
| 对话聊天 | 5 | 18 | ⭐⭐⭐ |
| 审计日志 | 1 | 4 | ⭐⭐ |
| 系统配置 | 2 | 6 | ⭐⭐ |
| LangGraph 工作流 | 3 | 12 | ⭐⭐⭐ |
| **总计** | **39** | **130** | — |

### 2.2 测试优先级说明

- **⭐⭐⭐ 高优先**：用户认证、权限校验、数据安全（第一阶段必须覆盖）
- **⭐⭐ 中优先**：审计日志、性能基准（第二阶段前覆盖）
- **⭐ 低优先**：边界情况、容错恢复（迭代期间持续完善）

---

## 三、测试执行清单

### 3.1 开发环节

| 环节 | 执行内容 | 负责 | 时机 |
|---|---|---|---|
| **单元测试** | `pytest tests/unit/` | 开发者 | 每次提交前 |
| **集成测试** | `pytest tests/integration/` | 开发者 | 功能完成后 |
| **代码覆盖率** | `pytest --cov=app` | CI | 每次 PR |
| **接口文档验证** | Swagger 与实现对齐 | 开发者 | 接口发布前 |

### 3.2 质量关卡

| 关卡 | 指标 | 阈值 | 触发 |
|---|---|---|---|
| **覆盖率** | 语句覆盖 | ≥ 75% | 代码合并前 |
| **安全** | SQL 注入、XSS | 零发现 | 每月一次 |
| **性能** | P95 响应时间 | < 500ms | 发版前 |
| **兼容性** | 与文档 API spec 对齐 | 100% | 接口变更后 |

---

## 四、测试环境依赖

### 4.1 本地运行

```bash
# 安装测试依赖
cd backend
uv add pytest pytest-asyncio pytest-cov pytest-mock httpx

# 配置测试数据库
export DATABASE_URL=postgresql://postgres:password@localhost/workpilot_test

# 执行所有测试
pytest

# 执行特定模块测试
pytest tests/integration/test_auth.py -v

# 生成覆盖率报告
pytest --cov=app --cov-report=html
```

### 4.2 CI/CD 集成

```yaml
# .github/workflows/test.yml
name: Backend Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:14-pgvector
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: cd backend && uv sync && pytest --cov
```

---

## 五、风险识别与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| JWT token 过期处理 | 会话中断 | 完整的 token 刷新流程测试 |
| Ollama 向量模型切换 | 向量空间不一致 | 模型切换后重新向量化的集成测试 |
| SSE 连接断开 | 用户体验差 | 断线重连、错误恢复测试 |
| 大文件处理超时 | 上传失败 | 200MB 边界值、超时处理测试 |
| 多 Worker 定时任务重复 | 数据污染 | APScheduler JobStore 并发测试 |
| 权限校验绕过 | 数据泄露 | 每个管理接口的权限穿透测试 |

---

## 六、测试文件组织

```
backend/
├── tests/
│   ├── conftest.py                 # 全局 fixtures
│   ├── unit/                       # 单元测试
│   │   ├── test_auth.py
│   │   ├── test_validators.py
│   │   └── test_utils.py
│   ├── integration/                # 集成测试
│   │   ├── test_auth_flow.py
│   │   ├── test_user_management.py
│   │   ├── test_document_pipeline.py
│   │   ├── test_chat_workflow.py
│   │   └── test_audit_logs.py
│   ├── e2e/                        # 端到端测试
│   │   ├── test_full_workflow.py
│   │   └── test_performance.py
│   └── fixtures/                   # 测试数据
│       ├── users.json
│       ├── documents.json
│       └── test_files/
│           ├── sample.md
│           ├── sample.pdf
│           └── sample.docx
├── pytest.ini                      # pytest 配置
└── .env.test                       # 测试环境变量
```

---

## 七、后续迭代计划

| 阶段 | 目标 | 预计工期 |
|---|---|---|
| 第 1 周 | 认证、用户、部门管理模块覆盖 ≥ 85% | 5 天 |
| 第 2 周 | 文档管理、对话模块覆盖 ≥ 80% | 5 天 |
| 第 3 周 | 集成测试、E2E 流程、性能基准 | 5 天 |
| 第 4 周+ | 边界场景、故障恢复、持续优化 | 持续 |

---

## 附录：快速开始

```bash
# 1. 安装依赖
cd backend && uv sync

# 2. 启动测试数据库
docker run --name workpilot_test -e POSTGRES_PASSWORD=password -d postgres:14-pgvector

# 3. 运行测试
pytest tests/ -v --cov=app

# 4. 查看覆盖率
open htmlcov/index.html
```
