# WorkPilot v2 — 唯一进度入口

> 设计细节见各需求文档；**功能是否做完、数字是否可信，只看本文件。**  
> 更新日期：2026-09-21

---

## 总览

| 模块 | 状态 | 备注 |
|---|---|---|
| 基础设施 + 场景 A–D + Q1–Q5 | ✅ | 见 git 历史 |
| Q6 R5 重排 | ⏸ | 门控样本曾不足；扩组后待复跑 |
| P1 LLM 可靠性 | ✅ 代码 | 重试/熔断/降级/并发 queued；单测通过；演练数字待填性能基线.md |
| P2 APScheduler + PG JobStore | ✅ 代码 | cleanup + 每日日报；**Windows 用 `uvicorn --workers 4`**（gunicorn 依赖 `fcntl`，仅 Linux/Docker） |
| P3 压测 | ✅ 脚本 / ⬜ 数字 | `scripts/loadtest/chat_loadtest.py`；表格见性能基线.md |
| P4 prompt 版本化 | ✅ | `backend/prompts/` + `prompt_set_version` 进 trace/eval_runs/diff |
| P5 embedding 切换 | ✅ 接口 / ⬜ 来回切验收 | 同维度 reembed API；异维度拒绝 |
| P6 CI | ✅ | unit + integration(pgvector) + 检索 eval fixture 门控（无 fixture 时 skip） |
| P7 注入防御 | ✅ 代码 | sanitizer + 边界 prompt + schema 校验 + 对抗语料/case + 安全设计.md |
| P8 演示 | ⬜ | README 已写默认外部 API 路径；GIF/公开 demo/干净 clone 待人工 |
| P9 部门日报 | ✅ 代码 | SQL 汇总 + LLM 摘要 + notifications；连续 3 天数字一致性待跑 |
| 门控/judge 复核数字 | ⬜ | Ollama 稳定后跑 gate_recheck + judge×2 |

---

## 生产就绪代码入口

| 能力 | 位置 |
|---|---|
| 重试/熔断/降级/排队 | `services/llm_resilience.py` + `llm_client.py` |
| 调度 | `services/scheduler.py`（APScheduler + SQLAlchemyJobStore） |
| 日报 | `services/daily_report.py` + `/api/admin/notifications` |
| Prompt 版本 | `backend/prompts/` + `services/prompt_loader.py` |
| 注入消毒 / schema 校验 | `doc_sanitizer.py` / `tools.base.validate_tool_args` |
| Embedding 切换 | `POST /api/admin/embedding/reembed` |
| 压测 / CI eval | `scripts/loadtest/` · `scripts/experiments/run_retrieval_eval_ci.py` |

---

## 评测数字（可引用 / 待复核）

| 指标 | 数值 | 可信度 |
|---|---|---|
| Q 前基线（72 case） | doc_hit@3 0.842 · mrr 0.648 | ✅ |
| Q1/Q2 后（82 case） | doc_hit@3 0.844 · mrr 0.669 · historical 1.0 | ✅ |
| distractor-topic mrr（扩组 n=10） | 待复跑 | ⚠️ |
| judge run12–14 | 3.36/45 → 3.80/27 → 3.80/24 | ⚠️ 待 2 次均值 |

---

## 明确不做

运维监控 / 客服 Agent、微服务拆分、GraphRAG、企业微信集成、前端重构。

---

## 文档索引

- [STATUS.md](STATUS.md)（本文件）
- [生产就绪需求.md](生产就绪需求.md)
- [安全设计.md](安全设计.md)
- [性能基线.md](性能基线.md)
- [系统架构.md](系统架构.md) / [API文档.md](API文档.md) / [业务场景设计.md](业务场景设计.md)
- [../README.md](../README.md)
