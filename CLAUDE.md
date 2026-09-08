# WorkPilot v2 — 企业智能 Agent 系统

## 项目概述

企业智能 Agent 系统，三大模块：
- **模块一** 运维监控 Agent（SSH 采集 + 告警 + 人工确认操作）
- **模块二** 内部知识库 Agent（员工 RAG 问答，第一阶段优先实现）
- **模块三** 客服 Agent（外部客户 API，第三阶段实现）

当前处于**第一阶段**：用户权限体系 + 模块二知识库 + 基础前端聊天界面。

完整需求文档见 [docs/需求文档.md](docs/需求文档.md)，系统架构见 [docs/系统架构.md](docs/系统架构.md)，API 文档见 [docs/API文档.md](docs/API文档.md)。

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
uv run fastapi dev main.py     # 开发启动（热重载，端口 8000）
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
data: {"type": "token", "content": "..."}
data: {"type": "sources", "content": [...]}
data: {"type": "done", "content": ""}
data: {"type": "error", "content": "错误信息"}
```

### 文档权限四级

| 级别 | 可见范围 |
|---|---|
| 全体共享 | 所有登录用户 |
| 非客服共享 | 除客服部门外所有成员 |
| 本部门共享 | 仅本部门成员 |
| 本部门指定人员 | 本部门内指定成员 |

检索时自动过滤，无权文档不参与召回且**不透露其存在**。

---

## 第一阶段交付范围

**后端（完整实现）：**
- 用户认证：JWT + bcrypt + 三级角色
- 文档管理：上传、解析（.md / .docx / .pdf）、分块、向量化、pgvector 存储
- RAG 问答：LangGraph 工作流（意图识别 → 检索 → 工具决策 → 工具执行 → 生成）、SSE 流式输出、引用来源
- 工具调用：3 个企业工具（员工信息 / 报销额度 / IT 工单）+ 权限校验 + 审计日志
- 评测回归：15 条 golden cases + eval runner + POST /api/eval/run
- 审计日志
- Docker Compose 部署

**前端（够用即可）：**
- 登录页
- 聊天主界面（发消息 + 流式显示 + 引用来源展示 + 工具调用展示）
- 历史会话列表

**暂不实现：** 运维监控、客服 Agent。

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
