# WorkPilot v2 后端测试代码生成完成

**生成日期：** 2026-06-01  
**总测试用例数：** 145+  
**覆盖的 API 端点：** 39 个  

---

## 📋 生成的文件清单

### 核心配置文件

| 文件 | 说明 |
|---|---|
| `pytest.ini` | pytest 配置文件（覆盖率、标记、日志等） |
| `.env.test` | 测试环境变量配置 |

### Fixtures & 工具函数

| 文件 | 说明 |
|---|---|
| `tests/conftest.py` | 全局 Fixtures（数据库、认证、Mock） |
| `tests/utils/__init__.py` | 工具函数包导出 |
| `tests/utils/auth_helpers.py` | Token 生成、过期 Token 等辅助函数 |
| `tests/utils/db_helpers.py` | 用户、部门创建等数据库辅助函数 |

### 单元测试（17 个用例）

| 文件 | 覆盖范围 | 用例数 |
|---|---|---|
| `tests/unit/test_auth.py` | 密码哈希、JWT 生成、验证规则 | 17 |

### 集成测试（122 个用例）

| 文件 | 覆盖范围 | 用例数 |
|---|---|---|
| `tests/integration/test_auth_integration.py` | 登录、登出、Token 刷新、密码修改、用户信息 | 25 |
| `tests/integration/test_user_management.py` | 用户列表、创建、修改、删除、权限管理 | 26 |
| `tests/integration/test_department_management.py` | 部门列表、创建、修改、删除、权限管理 | 17 |
| `tests/integration/test_document_management.py` | 文档上传、列表、处理状态、权限、删除 | 20 |
| `tests/integration/test_chat.py` | 流式对话、会话管理、权限过滤 | 16 |
| `tests/integration/test_audit_and_config.py` | 审计日志、系统配置读写 | 18 |

### 端到端测试（6 个场景）

| 文件 | 覆盖范围 |
|---|---|
| `tests/e2e/test_complete_workflow.py` | 完整工作流、权限级联、并发操作 |

### 文档

| 文件 | 说明 |
|---|---|
| `tests/README.md` | 测试指南（快速开始、命令、调试） |
| `TESTS_GENERATED.md` | 本文件 |

---

## 🎯 测试覆盖矩阵

### 按模块分布

```
认证模块          ████████████████████ 43 用例 (⭐⭐⭐ 高优先)
部门管理          ████████████ 18 用例 (⭐⭐⭐ 高优先)
用户管理          ██████████████████ 27 用例 (⭐⭐⭐ 高优先)
文档管理          ███████████████ 21 用例 (⭐⭐⭐ 高优先)
对话聊天          ███████████ 17 用例 (⭐⭐⭐ 高优先)
审计日志与配置     ███████████ 19 用例 (⭐⭐ 中优先)
────────────────────────────────────
总计              145 用例
```

### 按测试类型分布

```
单元测试          12% (17 用例)
集成测试          84% (122 用例)
端到端测试         4% (6 场景)
```

### 按优先级分布

```
⭐⭐⭐ 高优先      95% (138 用例)
⭐⭐ 中优先        5% (7 用例)
⭐ 低优先          0% (待补充)
```

---

## ✅ 关键测试场景

### 认证与权限

- ✅ 成功登录和密码验证
- ✅ 连续失败登录自动锁定（5 次）
- ✅ 禁用/启用账户
- ✅ Token 刷新与吊销
- ✅ 密码修改与首次改密
- ✅ 三级角色权限验证（超管/部门管理员/员工）
- ✅ 权限穿透测试（确保权限校验）

### 用户管理

- ✅ 用户创建（角色限制）
- ✅ 用户修改（不可改用户名、部门等）
- ✅ 用户重置密码
- ✅ 用户禁用/启用/解锁
- ✅ 强制登出
- ✅ 用户名/员工编号唯一性验证

### 部门管理

- ✅ 部门创建、修改、删除
- ✅ 部门代码不可修改
- ✅ 有用户/文档的部门无法删除
- ✅ 成员数量计数

### 文档管理

- ✅ 文件格式验证（MD/PDF/DOCX）
- ✅ 文件大小限制（≤200MB）
- ✅ 文档上传与处理状态轮询
- ✅ 文档权限四级管理（全体/非客服/本部门/指定人员）
- ✅ 权限过滤检索（无权限文档不可见）
- ✅ 文档归档与删除
- ✅ 元信息修改（分类、版本号）

### 对话聊天

- ✅ SSE 流式输出（conversation_id/token/sources/done 事件）
- ✅ 会话创建与继续对话
- ✅ 会话列表与搜索
- ✅ 会话重命名与删除
- ✅ 权限过滤（员工只见有权限的文档）
- ✅ 信息脱敏处理（调用外部 API 前）

### 系统操作

- ✅ 审计日志记录（所有关键操作）
- ✅ 审计日志查询与过滤
- ✅ 系统配置读写
- ✅ 权限基于角色的访问控制（RBAC）

### 并发与数据一致性

- ✅ 多用户并发对话
- ✅ 多用户并发操作（创建用户、查询列表）
- ✅ Token 并发刷新
- ✅ 数据一致性验证

---

## 📦 Fixtures 提供的能力

### 数据库隔离

- 每个测试在独立的数据库事务中执行
- 测试完成后自动回滚，不污染数据库
- 支持异步数据库操作

### 预置数据

```python
# 可用的预置用户
super_admin_user      # 超级管理员
dept_admin_user       # 部门管理员（属于 tech_department）
employee_user         # 普通员工（属于 tech_department）
multiple_employees    # 多个员工

# 可用的预置部门
tech_department       # 技术部（RD）
hr_department         # 人力资源部（HR）
multiple_departments  # 多个部门

# 对应的 Token
super_admin_token
dept_admin_token
employee_token
```

### Mock 服务

- Ollama 嵌入服务（向量化）
- Ollama 聊天服务（AI 回答）
- OpenAI API（外部 LLM）
- 文件存储服务
- PDF/DOCX 解析服务

---

## 🚀 快速开始

### 1. 安装依赖

```bash
cd backend
uv sync
```

### 2. 创建测试数据库

```bash
createdb workpilot_test
```

### 3. 运行测试

```bash
# 运行所有高优先级测试
pytest -m "high_priority" -v

# 运行特定模块
pytest tests/integration/test_auth_integration.py -v

# 生成覆盖率报告
pytest --cov=app --cov-report=html
```

---

## 🧪 测试命令速查表

```bash
# 基础命令
pytest                                    # 运行所有测试
pytest -v                                # 详细输出
pytest -s                                # 显示 print 输出

# 选择性运行
pytest -m "high_priority"                # 仅运行高优先级
pytest -m "integration"                  # 仅运行集成测试
pytest -m "not slow"                     # 跳过耗时测试

# 覆盖率
pytest --cov=app --cov-report=html      # 生成 HTML 报告
pytest --cov=app --cov-report=term      # 终端显示

# 调试
pytest -vvs --pdb                        # 进入调试器
pytest --lf                              # 运行最后失败的测试
pytest --ff                              # 失败优先

# 性能
pytest --durations=10                    # 显示最慢的 10 个测试
```

---

## 📊 预期覆盖率

根据测试用例设计：

| 指标 | 预期 |
|---|---|
| 语句覆盖率 | ≥ 80% |
| 分支覆盖率 | ≥ 75% |
| 函数覆盖率 | ≥ 85% |

---

## 🔗 相关文档

- [TESTING.md](TESTING.md) - 测试计划与策略
- [TEST_CASES.md](TEST_CASES.md) - 详细用例清单（139 个）
- [TESTING_FRAMEWORK.md](TESTING_FRAMEWORK.md) - 测试框架实现指南
- [tests/README.md](tests/README.md) - 测试运行指南

---

## 📝 开发工作流

1. **本地开发**：编写代码，运行 `pytest -m "high_priority"` 验证
2. **提交前**：运行 `pytest` 确保所有测试通过
3. **PR 前**：生成覆盖率报告，确保覆盖率 ≥ 75%
4. **CI/CD**：GitHub Actions 自动运行全量测试

---

## ⚠️ 注意事项

1. **数据库初始化**：测试自动创建表，但需要手动创建数据库
2. **环境变量**：确保 `.env.test` 中的数据库 URL 正确
3. **Mock 服务**：单元和集成测试使用 Mock，端到端测试可选使用真实服务
4. **异步测试**：所有集成测试都是异步的，需要 `pytest-asyncio`

---

## ✨ 亮点特性

- ✅ **全异步支持**：所有集成测试使用 AsyncClient
- ✅ **隔离数据库**：每个测试都在隔离的事务中
- ✅ **完整权限验证**：三级角色系统全覆盖
- ✅ **SSE 流式测试**：包含对话流式输出验证
- ✅ **Mock 完整**：外部 API 和文件操作都有 Mock
- ✅ **端到端场景**：包含完整业务流程验证
- ✅ **可扩展性强**：Fixtures 和工具函数易于复用

---

## 🎓 学习资源

本测试套件展示了以下最佳实践：

1. **Fixture 设计**：预置数据、Mock、隔离
2. **权限测试**：RBAC 系统的全面验证
3. **异步测试**：AsyncClient、流式响应处理
4. **数据库事务**：自动隔离与清理
5. **工具函数**：可复用的测试辅助

---

## 📞 支持

遇到问题？查看：

- `tests/README.md` 的 "常见问题" 部分
- [pytest 官方文档](https://docs.pytest.org/)
- [FastAPI 测试指南](https://fastapi.tiangolo.com/advanced/async-tests/)

---

**测试套件生成完成！所有代码可直接用于项目开发和 CI/CD 流水线。**
