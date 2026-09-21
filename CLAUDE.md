# WorkPilot v2 — 企业员工事务办理 Agent

## 项目概述

面向企业员工的事务办理 Agent：能查制度（RAG）、能算额度（工具）、能办申请（多步 + 人工确认）、能走审批（管理员后台）、可全程回溯（trace + 审计）。

**范围决策：** 集中资源把员工事务办理这一条垂直链路做深、做完整；运维监控与客服 Agent 仅作为 Roadmap，当前不实现。

**当前阶段：** 第一阶段基础设施（权限体系 + 知识库 RAG + 工具调用 + 评测）已完成，正在按 [docs/业务场景设计.md](docs/业务场景设计.md) 推进：
- 场景 A：报销申请预审 → 缺信息追问 → 人工确认 → 提交 → 审批（主场景）
- 场景 B：IT 工单闭环
- 场景 C：知识缺口分析 + 用户反馈
- 场景 D：权限差异化回答示例数据
- 配套工程：Agent 多步循环 + checkpointer + interrupt、节点级 trace、多轮查询改写、评测升级、混合检索

完整需求文档见 [docs/需求文档.md](docs/需求文档.md)，系统架构见 [docs/系统架构.md](docs/系统架构.md)，API 文档见 [docs/API文档.md](docs/API文档.md)，业务场景与补齐清单见 [docs/业务场景设计.md](docs/业务场景设计.md)。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ · FastAPI · Gunicorn + Uvicorn workers |
| 工作流 | LangGraph（Agent 状态机） |
| 数据库 | PostgreSQL 14+ + pgvector 扩展 |
| 向量检索 | pgvector（与关系数据同库，无独立向量库） |
| 本地模型 | Ollama（推理：Qwen2.5-7B；Embedding：nomic-embed-text） |
| 外部模型 | DeepSeek-V3 / Qwen-Max（仅管理员 / 复杂推理，调用前脱敏） |
| 实时通信 | SSE（对话流式输出） |
| 前端 | React + Ant Design Pro |
| 部署 | Docker + Docker Compose（nginx / frontend / backend / postgres / ollama） |
| SSH 采集 | Paramiko（运维模块） |
| 定时任务 | APScheduler + PostgreSQLJobStore（防多 Worker 重复执行） |

---

## 目录结构

```
v2/
├── backend/              # FastAPI 后端（当前开发主目录）
│   ├── main.py           # FastAPI 入口
│   ├── graph/            # LangGraph 工作流定义
│   │   ├── state.py      # 状态类型定义
│   │   ├── nodes.py      # 工作流节点函数
│   │   └── workflow.py   # 图的组装与编译
│   ├── tools/            # LangGraph 工具定义
│   ├── pyproject.toml    # uv 依赖管理
│   └── .env              # 本地环境变量（不提交）
├── frontend/             # React + Ant Design Pro
├── docs/                 # 项目文档目录
│   ├── API文档.md         # 接口文档（测试/开发参考）
│   ├── 需求文档.md         # 完整需求文档 v2.1
│   ├── 系统架构.md         # 架构决策（已确认，勿随意改动）
│   ├── 数据库设计.md       # 数据库设计决策
│   └── RAG流程与用例.md    # RAG 流程说明
├── start.ps1             # 一键启动脚本
├── stop.ps1              # 一键停止脚本
└── CLAUDE.md             # 本文件
```

---

## 开发环境

后端使用 **uv** 管理依赖，在 `backend/` 目录下操作：

```bash
cd backend
uv sync                        # 安装依赖
# Windows：uvicorn / fastapi dev（gunicorn 依赖 Unix fcntl，不能在 Windows 跑）
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
# 或 uv run fastapi dev main.py
# Linux/Docker 生产：
# uv run gunicorn -k uvicorn.workers.UvicornWorker -w 4 main:app -b 0.0.0.0:8000
uv add <package>               # 添加依赖
```

环境变量从 `backend/.env` 加载（参考 `.env.example`）。

---

## 架构关键约束（来自 docs/系统架构.md，已确认，不要违反）

1. **pgvector 替代独立向量库**：向量与结构化数据同 PostgreSQL 实例，权限过滤在同一 SQL 查询完成。
2. **Embedding 模型唯一性**：文档向量化和查询向量化必须用同一个 Ollama Embedding 模型，切换模型时需重新向量化全部文档。
3. **APScheduler 用 PostgreSQLJobStore**：Gunicorn 多 Worker 场景下防止定时任务重复执行。
4. **Nginx 关闭 proxy_buffering**：所有 `/api/*/stream` 路径必须关闭缓冲，`proxy_read_timeout` 设为 300s，保障 SSE 实时性。
5. **仅 Nginx 端口对外**：postgres(5432)、backend(8000)、ollama(11434) 均不对宿主机暴露。

---

## 核心设计规范

### 角色权限（三级）

| 角色 | 说明 |
|---|---|
| 超级管理员 | 唯一账号，全局所有权限，系统初始内置 |
| 部门管理员 | 由超级管理员创建，仅管本部门，不可访问运维模块 |
| 普通员工 | 仅聊天 + 个人历史记录 + 个人设置 |

权限校验**必须在服务端执行**，前端仅做展示控制。

### 用户名规范

- 格式：姓名全拼全小写，如 `zhangsan`
- 重名追加数字后缀：`zhangsan01`、`zhangsan02`
- 用户名创建后**不可修改**

### 安全要求

- 密码 bcrypt 哈希存储，禁止明文
- 调用外部 LLM API 前必须通过 LangGraph 脱敏节点（姓名→`[姓名]`，手机号→`[手机号]` 等）
- 运维命令执行严格白名单，防命令注入
- 所有关键操作写入 `audit_logs` 表，不可删除

### SSE 流式输出格式

```
data: {"type": "conversation_id", "content": "123"}
data: {"type": "token", "content": "..."}
data: {"type": "sources", "content": [...]}
data: {"type": "tool_call", "content": {"tool_name": "...", "tool_args": {...}, "allowed": true, "result": ..., "latency_ms": 0, "requires_confirmation": false, "missing_slots": null}}
data: {"type": "confirm_required", "content": {"tool_name": "submit_reimbursement_request", "payload": {"request_id": 1, "request_no": "RB-...", "form": {...}, "precheck": {...}}}}
data: {"type": "form_incomplete", "content": {"missing_slots": ["trip_start"], "message": "请补充：出差开始日期"}}
data: {"type": "done", "content": ""}
data: {"type": "error", "content": "错误信息"}
```

- `confirm_required`：写操作生成草稿后推送，前端渲染确认卡；确认调 `POST /api/reimbursements/{id}/confirm`，取消调 `cancel`
- `form_incomplete`：槽位缺失，前端提示补充字段后用户继续对话

### 文档权限四级

| 级别 | 可见范围 |
|---|---|
| 全体共享 | 所有登录用户 |
| 非客服共享 | 除客服部门外所有成员 |
| 本部门共享 | 仅本部门成员 |
| 本部门指定人员 | 本部门内指定成员 |

检索时自动过滤，无权文档不参与召回且**不透露其存在**。

---

## 交付范围

**已完成（第一阶段基础设施）：**
- 用户认证：JWT + bcrypt + 三级角色
- 文档管理：上传、解析（.md / .docx / .pdf）、分块、向量化、pgvector 存储
- RAG 问答：LangGraph 工作流（意图识别 → 检索 → 工具决策 → 工具执行 → 生成）、SSE 流式输出、引用来源
- 工具调用：3 个企业工具（员工信息 / 报销额度 / IT 工单）+ 权限校验 + 审计日志
- 评测回归：golden cases + eval runner + POST /api/eval/run
- 前端：登录、聊天（流式 + 引用 + 工具卡片）、历史会话、管理后台
- Docker Compose 部署

**进行中（按 [docs/业务场景设计.md](docs/业务场景设计.md) 的 P0 → P1 顺序）：**
- P0：Agent 多步循环 + Postgres checkpointer + 写操作 interrupt 人工确认；工具数据 DB 化 + seed 脚本；节点级 trace；多轮查询改写
- 场景 A 报销申请全链路 + 管理员审批后台
- P1：评测升级（Recall@K、LLM-as-judge、eval_runs 落库对比）、用户反馈、知识缺口页、混合检索、文档版本

**设计原则（实现新场景时遵守）：**
- LLM 只做决策和解释，数值校验、规则判断由代码完成
- 所有写操作工具标记 `requires_confirmation`，经 interrupt 由用户确认后才执行，且必须幂等
- 新增 SSE 事件类型需同步更新本文件「SSE 流式输出格式」和 API 文档

**不实现：** 运维监控、客服 Agent（仅 Roadmap）。

---

## LangGraph 工作流说明

当前 `backend/graph/` 已完成完整工作流，RAG + Tool Calling 流程节点顺序：

```
START ──┬──► anonymize ──────────────────┐
        └──► classify_intent ────────────┤
                                         ▼
                                       sync
                                         │
                            ┌─ chitchat ─┤
                            │            └─ rag ──► retrieve_docs ──► decide_tool
                            ▼                                              │
                  generate_chitchat                          ┌──────────────┼──────────────┐
                            │                                ▼              │              │
                            │                        execute_tool           │              │
                            │                                ▼              │              │
                            └──────────────────────────► generate_answer ◄─┘              │
                                      │                                                  │
                                      └──────────────────────────────────────────────── END
```

- `state.py` 定义 `TypedDict` 状态，所有节点共享同一状态对象
- `nodes.py` 每个节点为纯函数 `(state) -> state`
- `workflow.py` 组装 `StateGraph` 并编译为可执行图

---

## 数据库核心表（PostgreSQL）

```
users / departments / revoked_tokens
documents / doc_permissions / doc_chunks / embeddings（pgvector）
conversations / messages
tool_calls / it_tickets
visitor_sessions（客服模块，第三阶段）
servers / alerts / metrics_snapshots（运维模块，第二阶段）
audit_logs（不可删除）
system_config
```

---

## 对话历史上限（可配置）

| 配置项 | 默认值 |
|---|---|
| 每用户最大会话数 | 200 |
| 每会话最大消息数 | 500 |
| 归档数据保留时长 | 180 天 |

归档会话用户不可见，超级管理员审计时可查询。
