# WorkPilot v2 — 企业员工事务办理 Agent

面向企业员工的事务办理 Agent：能查制度、能算额度、能办申请、能走审批、可全程回溯。基于 FastAPI + LangGraph + PostgreSQL/pgvector 构建。

- **RAG 制度问答**：四级文档权限在同一条 SQL 内过滤；向量 + 关键词 RRF 混合检索
- **企业工具调用**：权限 + 幂等 + 审计；LLM 决策解释，数值校验由代码完成
- **事务办理闭环**：报销预审 → 缺信息追问 → 人工确认 → 提交 → 部门审批
- **可观测与可回归**：节点级 trace、golden case 评测落库、知识缺口反馈

进度与设计见 [docs/业务场景设计.md](docs/业务场景设计.md) 与 [docs/检索链路升级需求.md](docs/检索链路升级需求.md)。

## 快速启动

```powershell
# Windows（在 v2/ 目录）
.\dev.ps1 start          # postgres(Docker) + 后端 + 前端；Ollama 用本机

cd backend
uv run alembic upgrade head
uv run python scripts/seed_demo.py    # 部门/用户/规则/额度/制度文档
```

| 地址 | 说明 |
|---|---|
| http://localhost:5173 | 前端 |
| http://localhost:8000/docs | Swagger |
| http://localhost:8000/health | 健康检查 |

**演示账号**（`seed_demo.py`，密码 `Demo@12345`）：

| 用户 | 角色 | 用途 |
|---|---|---|
| zhangsan | employee / senior 研发 | 报销超标特批演示 |
| rdadmin | dept_admin 研发 | 审批本部门 / 工单处理 |
| admin | super_admin | 超管（初始密码见 `.env`） |

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ · FastAPI · uv |
| Agent | LangGraph（工具多步循环） |
| 数据库 | PostgreSQL + pgvector + tsvector（jieba 分词） |
| 模型 | Ollama 本地（qwen2.5:7b / nomic-embed-text）；可配外部 API + 管理员分档 |
| 前端 | React + Ant Design |
| 配置 | `config.yaml`（业务）+ `.env`（密钥） |

## 架构

```
用户问题
  → anonymize ∥ query_understand   # PII 记录；intent + 查询改写一次调用
  → 混合检索：向量候选扩展 ∥ jieba 关键词 → RRF → 分块合并（权限 SQL 内过滤）
  → decide_tool ⇄ execute_tool      # 多步循环；写操作 draft + confirm_required
  → generate_answer                 # 制度 + 工具结果注入 prompt
  → llm_client 出口脱敏（仅外部 API）
  → SSE：token / sources / tool_call / confirm_required / form_incomplete / qa_id
```

## 文档

| 文档 | 说明 |
|---|---|
| [docs/API文档.md](docs/API文档.md) | 接口、SSE 事件、错误码 |
| [docs/业务场景设计.md](docs/业务场景设计.md) | 场景 A–E、P0/P1 进度、设计决策 |
| [docs/检索链路升级需求.md](docs/检索链路升级需求.md) | R0–R5 检索升级与 eval 基线 |
| [docs/系统架构.md](docs/系统架构.md) | 架构约束 |
| [docs/数据库设计.md](docs/数据库设计.md) | 表结构决策 |

## 功能状态（2026-09-18）

| 功能 | 状态 |
|---|---|
| 认证 / 三级角色 / 部门 / 文档管理 | ✅ |
| RAG + SSE + 引用来源 | ✅ |
| 混合检索 RRF + 查询改写 + 分块合并 | ✅ |
| 模型分档 + 配置热加载 + 出口脱敏 | ✅ |
| 场景 A：报销预审→确认→审批 | ✅ |
| 场景 B：IT 工单闭环（创建/查询/后台处理） | ✅ |
| 场景 C：知识缺口 + 👍/👎 反馈 | ✅ |
| 场景 D：文档四级可见性 seed | ✅ |
| 节点级 trace + 管理后台 | ✅ |
| 评测 72 case + eval_runs 落库 | ✅ doc_hit@3=0.842 / mrr=0.648（诚实基线） |
| 混合检索 RRF + kw 配额 | ✅ E4 对照：比纯向量 mrr +0.22 |

## 工具一览

| 工具 | 类型 |
|---|---|
| query_employee_profile | 读 DB，员工只能查自己 |
| query_reimbursement_limit | 读 DB 额度 |
| precheck_reimbursement | 纯代码算超标/额度 |
| submit_reimbursement_request | 写 + 幂等 + requires_confirmation |
| query_my_reimbursements | 我的报销进度 |
| create_it_ticket / query_my_tickets | IT 工单创建与查询 |

## 评测

```powershell
# 超管；优先读 eval_cases 表（空则 cases.json）
curl -X POST "http://localhost:8000/api/eval/run?skip_generation=true&tool_dry_run=true" `
  -H "Authorization: Bearer <super_admin_token>"

# 导入 cases.json → eval_cases
curl -X POST "http://localhost:8000/api/quality/cases/seed" -H "Authorization: Bearer <token>"
```

- 指标：doc_hit@3 / recall@1 / mrr / intent / tool / citation / permission
- 语料：`backend/seed_docs` 24 份；**72 case** 分组
- **诚实基线（2026-09-18，配额开）：** doc_hit@3=0.842 · mrr=0.648 · intent/tool≈0.99/0.94 · permission=1.0
- 对照：纯向量 mrr 0.38 → 混合 RRF 0.60（检索子集）；详见 docs/检索链路升级需求.md

## 配置

| 文件 | 内容 |
|---|---|
| `backend/config.yaml` | LLM 提供商、超时、检索 top_k、限流等 |
| `backend/.env` | JWT 密钥、数据库 URL、OPENAI_API_KEY |

优先级：环境变量 > `.env` > `config.yaml` > 代码默认值。改 yaml/env 后后端自动热加载。

## Roadmap

员工事务链路稳定后扩展：运维监控 Agent、对外客服 Agent（同一套权限/工具/审计基础设施）。
