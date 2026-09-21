# WorkPilot v2 — 唯一进度入口

> 设计细节见各需求文档；**功能是否做完、数字是否可信，只看本文件。**  
> 更新日期：2026-09-20

---

## 总览

| 模块 | 状态 | 备注 |
|---|---|---|
| 基础设施（认证/RAG/工具/评测） | ✅ | 第一阶段 |
| 场景 A 报销闭环 | ✅ | 预审→确认→提交→审批 |
| 场景 B IT 工单 | ✅ | |
| 场景 C 知识缺口 | ✅ | |
| 场景 D 四级可见性 | ✅ | |
| Q1 文档生命周期 | ✅ | 代码+seed+eval；**门控结论待复核**（见下） |
| Q2 多轮工具决策 | ✅ | session_tool_calls + draft 复用 |
| Q3 LLM-as-judge | ✅ | 三轮 run；**hallu 差异待复核**（样本/噪声） |
| Q4 评测管理界面 | ✅ | 超管 Tab：case/run/diff |
| Q5 README/演示 | ✅ 文档 / ⬜ GIF | 架构图与跑通说明在 README；GIF 需录屏 |
| Q6 R5 重排 | ⏸ 搁置 | 门控样本不足，**不作最终结论** |
| 父块召回（小块检索大块生成） | ✅ 代码 | `retrieval_parent_expand`；效果需 2 次 judge 均值 |
| 文档提示注入防御 | ✅ 代码 | sanitizer + prompt + 单测 + injection case |
| supersedes 权限 | ✅ | dept_admin 不可跨部门/下架 global；集成测试 `test_doc_lifecycle_authz.py` |
| CI 集成测试 | ✅ workflow | pgvector service + documents/users/departments/lifecycle |
| 父块/门控/judge 复核数字 | ⬜ | 代码与 case 已备好，待 Ollama 稳定后跑 2 次 |

---

## 评测数字（可引用 / 待复核）

| 指标 | 数值 | 可信度 |
|---|---|---|
| Q 前基线（72 case） | doc_hit@3 0.842 · mrr 0.648 | ✅ 历史 run |
| Q1/Q2 后（82 case） | doc_hit@3 0.844 · mrr 0.669 · historical 1.0 | ✅ 单次全量 |
| distractor-topic mrr=1.0（n=2） | 门控触发依据 | ⚠️ **待复核**：case 已扩到 n=10（2026-09-21），完整重跑因 Ollama embedding 中断未完成 |
| distractor-lifecycle mrr=0.42（n=3） | 参考 | ⚠️ case 已扩到 n=9；完整重跑待 Ollama 稳定后执行 |
| judge faith/hallu run12–14 | 3.36/45 → 3.80/27 → 3.80/24 | ⚠️ **待复核**：同配置 2 次均值再判 run14 是否有效 |
| multiturn tool_acc 0.923 | n=13 | ✅ 单次；新增 Q2 case 通过 |

**门控复核（2026-09-21）：** case 集已扩至 98（topic 10 / lifecycle 9 / injection 2）；`scripts/experiments/run_gate_recheck.py` 开跑后 Ollama embedding 中途 `ConnectError`，本次**不采信**。请在 Ollama 稳定后重跑：

```bash
cd backend
uv run python scripts/seed_eval_cases.py
uv run python scripts/experiments/run_gate_recheck.py
# judge 2 次：
uv run python scripts/experiments/run_q3_judge.py
uv run python scripts/experiments/run_q3_judge.py
```

脚本：

```bash
cd backend
uv run python scripts/seed_eval_cases.py
uv run python scripts/experiments/run_q1_q2_eval.py
uv run python scripts/experiments/run_q3_judge.py
```

实验脚本目录：`backend/scripts/experiments/`。

---

## 代码入口速查

| 能力 | 位置 |
|---|---|
| lifecycle 检索过滤 | `services/retriever.py` `build_lifecycle_clause` |
| 父块扩展 | `services/retriever.py` `_expand_parent_sections` |
| time_scope | `graph/nodes.py` `query_understand_node` |
| session_tool_calls | `api/chat.py` + `graph/nodes.py` `decide_tool_node` |
| LLM-as-judge | `eval/judge.py` + `POST /api/eval/run?mode=judge` |
| 评测 UI | `frontend/src/pages/admin/EvalTab.tsx` |
| 注入消毒 | `services/doc_sanitizer.py` |
| supersedes 鉴权 | `api/documents.py` `_check_supersedes_scope` |

---

## 明确不做 / 以后再说

| 项 | 原因 |
|---|---|
| 运维监控 Agent / 客服 Agent | 范围决策：Roadmap only |
| R5 重排 sidecar | 门控未确认前不实现 |
| 会话记忆摘要、成本看板 | P2，主体已够 |
| 干净 clone + GIF 录制 | 依赖本机人工 |

---

## 文档索引（只保留设计，不再维护 ✅/⬜）

- [docs/系统架构.md](系统架构.md)
- [docs/数据库设计.md](数据库设计.md)
- [docs/API文档.md](API文档.md)
- [docs/业务场景设计.md](业务场景设计.md)
- [docs/答案质量与文档生命周期需求.md](答案质量与文档生命周期需求.md)
- [docs/检索链路升级需求.md](检索链路升级需求.md)
- [../README.md](../README.md)
