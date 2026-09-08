# WorkPilot v2 — 企业智能 Agent 系统

基于 FastAPI + LangGraph + PostgreSQL/pgvector 构建的企业内部 Agent 系统，支持知识库问答、权限控制、审计日志和 SSE 流式输出。

## 快速启动

```powershell
# Windows（在 v2/ 目录）
.\start.ps1     # 启动所有服务
.\stop.ps1      # 停止所有服务
```

启动后访问：

| 地址 | 说明 |
|---|---|
| http://localhost:5173 | 前端界面 |
| http://localhost:8000/docs | Swagger API 文档 |
| http://localhost:8000/health | 健康检查 |

初始管理员：`admin` / `Admin@123`（首次登录强制改密）

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 · FastAPI · Gunicorn + Uvicorn |
| Agent 工作流 | LangGraph |
| 数据库 | PostgreSQL 14 + pgvector |
| 本地模型 | Ollama（qwen2.5:7b 推理 + nomic-embed-text 向量化） |
| 前端 | React + Ant Design |
| 部署 | Docker Compose |

## 架构

```
用户问题
  → 脱敏节点（PII 替换）
  → 意图分类（闲聊 / RAG）
  → 权限过滤向量检索（pgvector）
  → LLM 生成回答（Ollama qwen2.5:7b）
  → SSE 流式推送
```

## 文档

| 文档 | 说明 |
|---|---|
| [docs/API文档.md](docs/API文档.md) | 接口说明、错误码、测试流程 |
| [docs/需求文档.md](docs/需求文档.md) | 完整产品需求 |
| [docs/系统架构.md](docs/系统架构.md) | 架构决策与约束 |
| [docs/数据库设计.md](docs/数据库设计.md) | 数据库设计说明 |
| http://localhost:8000/docs | Swagger（始终与代码同步） |

## 开发

```bash
# 后端（在 backend/ 目录）
uv sync
uv run fastapi dev main.py

# 前端（在 frontend/ 目录）
npm install
npm run dev
```

## 功能状态

| 功能 | 状态 |
|---|---|
| 用户认证（JWT + bcrypt + 三级角色） | ✅ Phase 1 |
| 部门管理 | ✅ Phase 1 |
| 文档上传 + 解析 + 向量化 | ✅ Phase 1 |
| RAG 问答 + SSE 流式输出 | ✅ Phase 1 |
| 前端：聊天 + 历史 + 管理后台 | ✅ Phase 1 |
| 审计日志（写入） | ✅ Phase 1 |
| 工具调用（3 个企业工具 + 权限校验） | ✅ Phase 1 |
| 评测回归（15 条 golden cases + 指标） | ✅ Phase 1 |
| PII 脱敏（密钥/身份证/手机号/邮箱） | ✅ Phase 1 |
| 运维监控 Agent | ⏳ Phase 2 |
| 客服 Agent | ⏳ Phase 3 |

## 工具调用

系统支持 3 个企业工具：

| 工具 | 说明 | 权限 |
|---|---|---|
| query_employee_profile | 查询员工基本信息 | 所有角色（只能查自己） |
| query_reimbursement_limit | 查询报销额度 | 所有角色（只能查自己） |
| create_it_ticket | 创建 IT 工单（幂等） | 所有角色 |

调用流程：用户提问 → 意图识别 → 检索 → LLM 判断工具需求 → 权限校验 → 执行 → 生成回答

## 评测

```bash
curl -X POST http://localhost:8000/api/eval/run \
  -H "Authorization: Bearer <super_admin_token>"
```

指标：意图准确率、文档命中率、工具调用准确率、引用覆盖率
