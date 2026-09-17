# WorkPilot v2 — 企业员工事务办理 Agent

面向企业员工的事务办理 Agent：能查制度、能算额度、能办申请、能走审批、可全程回溯。基于 FastAPI + LangGraph + PostgreSQL/pgvector 构建，核心能力：

- **RAG 制度问答**：四级文档权限在同一条 SQL 内过滤，无权文档不参与召回也不透露存在
- **企业工具调用**：权限校验 + 幂等 + 审计，LLM 只负责决策和解释，数值校验由代码完成
- **事务办理闭环**：报销预审 → 缺信息追问 → 人工确认 → 提交 → 管理员审批（见 [业务场景设计](docs/业务场景设计.md)）
- **可观测与可回归**：节点级 trace、golden case 评测、用户反馈驱动的知识缺口分析

> 当前正在按 [docs/业务场景设计.md](docs/业务场景设计.md) 推进场景 A（报销申请）与配套工程能力，进度见下方「功能状态」。

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
  → 脱敏节点（PII 替换，仅用于外部 LLM）‖ 意图分类（闲聊 / RAG）   ← 并行
  → 权限过滤向量检索（pgvector）
  → 工具决策 → 权限校验 → 工具执行（写操作前人工确认）
  → LLM 生成回答（Ollama qwen2.5:7b，带引用来源）
  → SSE 流式推送
```

## 文档

| 文档 | 说明 |
|---|---|
| [docs/API文档.md](docs/API文档.md) | 接口说明、错误码、测试流程 |
| [docs/需求文档.md](docs/需求文档.md) | 完整产品需求 |
| [docs/系统架构.md](docs/系统架构.md) | 架构决策与约束 |
| [docs/数据库设计.md](docs/数据库设计.md) | 数据库设计说明 |
| [docs/业务场景设计.md](docs/业务场景设计.md) | 业务场景设计、工程需求清单、实施顺序、设计决策说明 |
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
| 用户认证（JWT + bcrypt + 三级角色） | ✅ |
| 部门管理 | ✅ |
| 文档上传 + 解析 + 向量化 | ✅ |
| RAG 问答 + SSE 流式输出 + 引用来源 | ✅ |
| 前端：聊天 + 历史 + 管理后台 | ✅ |
| 审计日志（写入） | ✅ |
| 工具调用（3 个企业工具 + 权限校验 + 幂等） | ✅ |
| 评测回归（golden cases + 指标） | ✅ 基础版 |
| PII 脱敏（密钥/身份证/手机号/邮箱） | ✅ |
| 场景 A：报销申请预审 → 确认 → 提交 → 审批 | 🚧 进行中 |
| Agent 多步循环 + checkpointer + 人工确认（interrupt） | 🚧 进行中 |
| 节点级 trace | ⏳ |
| 多轮查询改写 | ⏳ |
| 场景 B：IT 工单闭环 | ⏳ |
| 场景 C：知识缺口分析 + 用户反馈 | ⏳ |
| 评测升级（Recall@K、LLM-as-judge、结果落库对比） | ⏳ |
| 混合检索（向量 + 全文 RRF） | ⏳ |

## Roadmap

在员工事务 Agent 稳定后，基于同一套权限 / 工具 / 审计基础设施扩展：运维监控 Agent（SSH 采集 + 告警 + 人工确认执行）、对外客服 Agent（API Key 体系）。

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
