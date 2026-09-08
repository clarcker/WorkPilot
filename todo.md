
---

# 15 天 L2 Agent 求职项目执行文档

## 1. 目标定位

### 1.1 求职目标

目标岗位不是最低级 Demo 型 Agent 开发，而是：

> **L2 生产级 Agent 应用工程师 / 垂直场景 AI 后端工程师**

这个层级要求你不只是会调用大模型 API，也不只是能做 RAG Demo，而是要证明你具备：

- 后端服务封装能力
- RAG 工程化能力
- Tool Calling 工程化能力
- Workflow / 状态流编排能力
- 权限校验与审计意识
- 日志追踪与失败排查能力
- 简单评测回归能力
- 能解释“为什么这么设计”

### 1.2 15 天目标

15 天后必须达到：

> 简历上能写一个 Agent 项目，GitHub 有可运行代码，README 能说明设计，面试时能围绕项目讲 10-15 分钟，并能回答常见追问。

不是目标：

- 不是学完所有 Agent 框架
    
- 不是做完整企业平台
    
- 不是做复杂多 Agent 系统
    
- 不是做漂亮前端
    
- 不是做论文级创新
    

核心目标是：

> **小而完整，具备 L2 工程意识。**

---

# 2. 项目选择

## 2.1 项目名称

**Enterprise Workflow Agent**

中文名：

> 企业内部知识与流程执行 Agent

## 2.2 一句话介绍

> 基于 FastAPI + LangGraph + PostgreSQL/pgvector 构建企业内部 Agent 后端系统，支持制度知识库问答、工具调用、权限校验、审计日志、失败降级和评测回归。

## 2.3 为什么选这个项目

这个项目比普通 RAG 问答更适合 L2 岗位，因为它覆盖了真实企业 Agent 的关键问题：

|能力|普通 RAG Demo|Enterprise Workflow Agent|
|---|---|---|
|知识问答|有|有|
|工具调用|通常没有|有|
|状态流编排|通常没有|有|
|权限控制|通常没有|有|
|审计日志|通常没有|有|
|失败降级|通常没有|有|
|评测回归|通常没有|有|
|面试可展开性|一般|强|

## 2.4 为什么不做 Research Agent

暂时不选 Multi-tool Research Agent，原因：

1. 开放网页搜索容易把时间浪费在搜索 API、网页抓取、反爬、网页清洗上。
    
2. 业务场景太泛，面试时不好体现企业 Agent 落地能力。
    
3. 权限、审计、流程执行这些 L2 关键能力不突出。
    
4. 15 天内更容易做成“看起来能跑，但像玩具”的 Demo。
    

---

# 3. 技术栈

## 3.1 核心技术栈

|模块|技术|
|---|---|
|后端服务|FastAPI|
|Agent 工作流|LangGraph|
|RAG 存储|PostgreSQL + pgvector|
|数据库|PostgreSQL|
|缓存|Redis，可选，不作为核心|
|模型调用|OpenAI / Anthropic / 兼容 API|
|评测|自写 eval runner|
|部署|Docker Compose|
|文档|README + eval_report.md|

## 3.2 为什么用 Python

用 Python，不用 Go。

原因：

1. Agent 岗位默认主语言就是 Python。
    
2. LangGraph、LangChain、LlamaIndex、RAG 生态主要围绕 Python。
    
3. 你已有 Go 后端优势，但这个项目要服务求职岗位预期。
    
4. Go 优势可以在面试中体现为：并发、系统设计、服务稳定性、后端工程经验。
    

## 3.3 LangGraph 的定位

LangGraph 不是用来“偷懒调包”，而是用来表达：

> 我把 Agent 任务拆成了可控的状态流，而不是让大模型在一个黑盒 prompt 里自由发挥。

你必须能解释：

- State 里保存什么
    
- 每个 node 负责什么
    
- 哪些 node 由 LLM 决策
    
- 哪些 node 必须代码确定性处理
    
- 为什么工具调用前要经过权限校验
    
- 为什么要记录 trace
    

---

# 4. 项目核心功能范围

## 4.1 P0：必须完成

没有这些，项目不成立，也不建议写进简历：

- [x] 1. FastAPI `/chat` 接口 ✅ SSE 流式输出
- [x] 2. LangGraph 主流程 ✅ 10 节点（anonymize → classify_intent → sync → retrieve_docs → decide_tool → execute_tool → generate_answer）
- [x] 3. RAG 检索企业文档 ✅ pgvector + 4 级权限过滤
- [x] 4. 3 个 mock 企业工具 ✅ query_employee_profile / query_reimbursement_limit / create_it_ticket
- [x] 5. 工具调用前权限校验 ✅ ToolRegistry.execute 内置权限检查
- [x] 6. trace 日志记录 ✅ 工具调用审计日志写入 audit_logs 表
- [x] 7. README 基础说明 ✅ 含工具调用 + 评测章节
    

最低主流程：

```text
用户问题
→ 意图识别
→ RAG 检索
→ 判断是否需要工具
→ 权限校验
→ 工具调用
→ 答案生成
→ trace 记录
```

## 4.2 P1：15 天内尽量完成

这些决定你是不是像 L2，而不是普通 Demo：

- [x] 1. 15-20 条 eval cases ✅ 15 条 golden cases（6 制度问答 + 4 工具调用 + 3 闲聊 + 2 混合）
- [x] 2. eval_report.md ✅ POST /api/eval/run 返回 intent_accuracy / doc_hit_rate / tool_call_accuracy / citation_rate
- [x] 3. 失败降级 ✅ LLM 不可用时关键词降级、工具执行异常捕获、检索无结果兜底
- [x] 4. 审计日志 ✅ 所有工具调用写入 audit_logs（TOOL_CALL / TOOL_DENY）
- [x] 5. README 完整版 ✅ 含工具调用 + 评测 + 架构说明
- [ ] 6. 简历项目描述
- [ ] 7. 面试问题答案
    

## 4.3 P2：投递后继续补

这些是加分项，但不影响先投递：

1. Redis 缓存
    
- [x] 2. asyncio 并发工具调用 ✅ LangGraph 并行节点（anonymize + classify_intent）
- [x] 3. Streaming response ✅ SSE 流式输出（token / sources / tool_call / done / error）
4. LangSmith 接入
    
5. demo 视频
    
6. 更多 eval cases
    

## 4.4 P3：现在不要做

15 天内禁止碰：

```text
多 Agent
MCP
复杂 Memory
前端页面
Kubernetes
模型微调
真实企业 API
开放网页搜索
复杂权限平台
```

---

# 5. 系统设计

## 5.1 目录结构

```text
enterprise-workflow-agent/
  app/
    main.py
    graph/
      state.py
      nodes.py
      workflow.py
    rag/
      loader.py
      splitter.py
      embedder.py
      retriever.py
    tools/
      registry.py
      employee.py
      reimbursement.py
      ticket.py
    auth/
      permission.py
    trace/
      logger.py
      models.py
    eval/
      cases.json
      runner.py
  docs/
    reimbursement_policy.md
    leave_policy.md
    device_repair_policy.md
    access_control_policy.md
    onboarding_guide.md
  README.md
  eval_report.md
  docker-compose.yml
  requirements.txt
```

## 5.2 核心接口

最低实现 3 个接口：

```text
POST /chat
GET  /sessions/{session_id}/trace
POST /eval/run
```

可选：

```text
POST /documents/index
GET  /health
```

## 5.3 LangGraph 状态设计

```python
class AgentState(TypedDict):
    session_id: str
    user_id: str
    role: str
    question: str

    intent: str
    retrieved_docs: list

    need_tool: bool
    tool_name: str | None
    tool_args: dict
    tool_result: dict | None

    permission_result: dict
    final_answer: str

    error: str | None
    trace: list
```

## 5.4 Workflow 节点

```text
classify_intent
retrieve_docs
decide_tool
check_permission
execute_tool
generate_answer
record_trace
handle_error
```

## 5.5 哪些交给 LLM，哪些必须代码控制

|节点|处理方式|原因|
|---|---|---|
|意图识别|LLM|语义判断适合模型|
|RAG 检索|代码|检索必须可控|
|是否需要工具|LLM + 规则|先模型判断，再规则约束|
|权限校验|代码|安全逻辑不能交给模型|
|工具执行|代码|工具有副作用，必须受控|
|答案生成|LLM|语言表达适合模型|
|trace 记录|代码|追踪必须稳定可靠|

---

# 6. RAG 设计

## 6.1 文档范围

准备 5 篇模拟企业文档：

```text
reimbursement_policy.md     报销制度
leave_policy.md             请假制度
device_repair_policy.md     设备维修制度
access_control_policy.md    权限制度
onboarding_guide.md         入职指南
```

## 6.2 RAG 最小能力

必须实现：

1. Markdown 文档加载
    
2. chunk 切分
    
3. embedding
    
4. pgvector 存储
    
5. top-k 检索
    
6. metadata 保存
    
7. 答案引用来源
    

返回示例：

```json
{
  "answer": "根据报销制度，差旅住宿报销标准根据城市级别不同而不同。",
  "citations": [
    {
      "doc": "reimbursement_policy.md",
      "chunk_id": "reimburse_003"
    }
  ]
}
```

## 6.3 面试要能解释

你必须能回答：

1. 为什么要切 chunk？
    
2. chunk 太大有什么问题？
    
3. chunk 太小有什么问题？
    
4. 为什么要保存 metadata？
    
5. 为什么答案要带 citation？
    
6. 检索不到怎么办？
    
7. 检索结果有噪声怎么办？
    

---

# 7. Tool Calling 设计

## 7.1 必须实现的 3 个工具

```text
query_employee_profile(user_id)
query_reimbursement_limit(user_id, category)
create_it_ticket(user_id, issue_type, description)
```

全部使用 mock 数据，不接真实企业系统。

## 7.2 每个工具必须包含

1. 工具名称
    
2. 工具描述
    
3. 参数 schema
    
4. 参数校验
    
5. 权限要求
    
6. 错误返回
    
7. 调用日志
    
8. 超时处理
    
9. 审计字段
    

## 7.3 create_it_ticket 必须有幂等

原因：

> 创建类工具有副作用，模型可能重复调用。如果没有幂等，会重复创建工单。

简单实现：

```text
idempotency_key = user_id + issue_type + hash(description)
```

如果重复提交，返回已有工单。

## 7.4 面试要能解释

你必须能回答：

1. 工具误调用怎么防？
    
2. 参数缺失怎么办？
    
3. 工具超时怎么办？
    
4. 工具返回错误怎么办？
    
5. 为什么 create 类工具要幂等？
    
6. 为什么不能让 LLM 直接绕过权限执行工具？
    

---

# 8. 权限与审计设计

## 8.1 角色设计

只做最小权限模型：

```text
employee
manager
admin
```

## 8.2 权限规则

```text
employee 只能查自己的信息
manager 可以查部门工单汇总
admin 可以查看审计日志
```

## 8.3 审计日志字段

```text
session_id
user_id
role
tool_name
tool_args
allowed
reason
latency_ms
error
created_at
```

## 8.4 权限拒绝示例

用户：

```text
帮我查一下 user_002 的报销额度
```

如果当前用户是普通 employee，返回：

```json
{
  "answer": "你没有权限查询该员工的报销额度。",
  "permission": "denied"
}
```

## 8.5 面试表达重点

你要强调：

> 我没有把 Agent 当成一个无权限聊天机器人，而是把工具调用纳入权限校验和审计体系。模型可以建议调用工具，但是否允许执行由代码决定。

---

# 9. Trace 与日志设计

## 9.1 为什么必须做 trace

L2 和 Demo 的区别之一是：

> 出错之后能不能知道错在哪里。

trace 要能回答：

1. 用户问了什么？
    
2. 被识别成什么意图？
    
3. 检索到了哪些文档？
    
4. 是否决定调用工具？
    
5. 调用了哪个工具？
    
6. 参数是什么？
    
7. 是否通过权限校验？
    
8. 工具结果是什么？
    
9. 哪一步失败？
    
10. 总耗时多少？
    

## 9.2 trace 记录字段

```text
session_id
node_name
input
output
latency_ms
error
created_at
```

## 9.3 trace 示例

```json
{
  "session_id": "s_001",
  "steps": [
    {
      "node": "classify_intent",
      "output": "reimbursement_query",
      "latency_ms": 320
    },
    {
      "node": "retrieve_docs",
      "output": ["reimbursement_policy.md"],
      "latency_ms": 120
    },
    {
      "node": "execute_tool",
      "tool": "query_reimbursement_limit",
      "latency_ms": 80
    }
  ]
}
```

---

# 10. 失败处理与降级

## 10.1 必须覆盖的失败场景

|场景|处理策略|
|---|---|
|RAG 无结果|提示无法基于知识库确认|
|工具超时|返回制度说明，不返回个人数据|
|工具参数缺失|要求用户补充必要参数|
|权限不足|拒绝工具调用，但可返回公开制度|
|LLM 输出 JSON 格式错误|重试一次，仍失败返回结构化错误|
|重复创建工单|幂等检查，返回已有工单|

## 10.2 面试表达重点

你要强调：

> Agent 系统不能只考虑成功路径。真实业务里，检索失败、工具失败、权限不足都很常见，所以我把失败处理设计进了 workflow，而不是靠临时 prompt 补救。

---

# 11. Eval 回归设计

## 11.1 为什么要做 eval

L2 项目必须体现：

> 系统修改后，怎么知道没有变差？

eval 不需要复杂，但必须有。

## 11.2 eval cases 分布

准备 15-20 条：

```text
6 条制度问答
4 条工具调用
3 条权限拒绝
2 条工具失败
2 条混合问题
```

## 11.3 指标

```text
intent_accuracy
doc_hit_rate
tool_call_accuracy
permission_pass_rate
citation_rate
failed_cases
```

## 11.4 eval_report.md 示例

```text
intent_accuracy:       85%
doc_hit_rate:          80%
tool_call_accuracy:    90%
permission_pass_rate: 100%
citation_rate:         85%

failed_cases:
- case_007: intent 判断错误
- case_012: 检索命中文档错误
```

## 11.5 面试表达重点

你要说：

> 我用 golden cases 做最小回归测试，覆盖制度问答、工具调用、权限拒绝和失败场景。每次改 prompt、chunk 或工具描述后，都可以跑 eval 看是否回退。

---

# 12. 15 天执行计划

## 第 1 天：项目初始化

目标：

> 项目正式启动，不再纠结方向。

任务：

```text
创建 GitHub repo
搭 FastAPI
实现 /chat mock
建立目录结构
写 README 第一版
完成第一个 commit
```

验收：

```text
/chat 能返回 mock answer
README 写清项目目标
```

---

## 第 2 天：LangGraph 最小流程

目标：

> workflow 能跑。

任务：

```text
定义 AgentState
实现 classify_intent mock
实现 retrieve_docs_mock
实现 generate_answer
接入 /chat
记录简单 trace
```

验收：

```text
用户输入 → LangGraph → 返回结构化结果
trace 能看到每个节点
```

---

## 第 3-4 天：RAG 最小闭环

目标：

> 制度问答能基于文档回答。

任务：

```text
准备 5 篇 markdown 文档
实现文档加载
实现 chunk 切分
接 embedding
写入 pgvector
实现 top-k 检索
答案带 citation
```

验收：

```text
问报销制度，能命中 reimbursement_policy.md
返回答案带 citations
```

止损：

```text
pgvector 卡住超过 2 小时，先换 Chroma / FAISS / 内存检索跑通。
```

---

## 第 5-6 天：Tool Calling

目标：

> 工具调用跑通。

任务：

```text
实现 ToolRegistry
实现 query_employee_profile
实现 query_reimbursement_limit
实现 create_it_ticket
加入参数校验
加入错误返回
加入调用日志
```

验收：

```text
问“查我的差旅报销额度”
→ 识别意图
→ 检索制度
→ 调用工具
→ 返回制度说明 + 个人额度
```

---

## 第 7 天：主流程整合

目标：

> 端到端跑通。

任务：

```text
串联 classify_intent
串联 retrieve_docs
串联 decide_tool
串联 check_permission
串联 execute_tool
串联 generate_answer
串联 record_trace
```

验收必须有 3 个示例：

```text
1 个纯 RAG 问答
1 个 RAG + 工具调用
1 个权限拒绝
```

第 7 天是关键检查点。

如果这天没跑通：

```text
砍掉 Redis、streaming、并发、LangSmith、demo 视频。
只保主流程。
```

---

## 第 8-9 天：权限与审计

目标：

> 项目从 Demo 变成企业场景原型。

任务：

```text
实现 employee / manager / admin
实现权限规则
工具调用前鉴权
记录 audit log
实现 /sessions/{session_id}/trace
```

验收：

```text
employee 查别人信息 → 拒绝
admin 查 trace → 允许
所有工具调用都有 audit log
```

---

## 第 10 天：失败处理与降级

目标：

> 体现生产化意识。

任务：

```text
处理 RAG 无结果
处理工具超时
处理参数缺失
处理权限不足
处理 LLM JSON 格式错误
处理重复创建工单
```

验收：

```text
README 增加 Failure Handling & Fallback Strategy
代码中有明确 fallback 分支
```

---

## 第 11-12 天：Eval 回归

目标：

> 做出 eval_report.md。

任务：

```text
写 15-20 条 eval cases
实现 eval runner
输出指标
记录 failed_cases
生成 eval_report.md
```

验收：

```text
能运行 POST /eval/run
能输出 intent/doc/tool/permission/citation 指标
```

---

## 第 13 天：README 完整化

目标：

> GitHub 项目看起来像正式工程项目。

README 必须包含：

```text
1. 项目背景
2. 为什么不是普通 RAG
3. 架构图
4. 技术栈
5. 核心流程
6. RAG 设计
7. Tool Calling 设计
8. 权限与审计
9. Trace 日志
10. Eval 结果
11. 失败降级
12. 本地启动方式
13. 示例请求和响应
```

架构图：

```text
User
 ↓
FastAPI /chat
 ↓
LangGraph Workflow
 ├─ Intent Node      LLM
 ├─ RAG Node         pgvector
 ├─ Tool Decision    LLM + rule
 ├─ Permission Node  code
 ├─ Tool Execute     code
 └─ Answer Node      LLM
 ↓
Trace / Audit Log
```

---

## 第 14 天：简历与面试话术

目标：

> 项目能写进简历，能讲出来。

### 简历项目描述

```text
企业内部知识与流程执行 Agent

基于 FastAPI + LangGraph + PostgreSQL/pgvector 构建企业内部 Agent 后端系统，支持制度知识库问答、工具调用、权限校验、审计日志和评测回归。系统将意图识别、RAG 检索、工具决策、权限校验、工具执行和答案生成拆分为 LangGraph 状态节点，降低单轮 Prompt 黑盒执行风险。RAG 模块支持 Markdown 文档切分、向量检索、metadata 过滤和引用溯源；工具层模拟员工信息查询、报销额度查询、IT 工单创建等企业 API，并加入参数校验、超时处理、幂等控制和审计日志。构建 15-20 条 golden cases，对意图识别、文档命中、工具调用、权限拒绝和引用覆盖进行回归评测，支持失败样例复盘。
```

### 必备面试问题

每题准备 1 分钟答案：

```text
1. 为什么选 LangGraph，不用纯 ReAct while loop？
2. 这个项目和普通 RAG 问答有什么区别？
3. RAG chunk 怎么设计？chunk size 怎么定？
4. 工具误调用怎么防？
5. 权限怎么做？
6. 工具失败怎么降级？
7. 怎么评测 Agent 效果？
8. 一次错误回答怎么排查？
9. 哪些地方不让 LLM 决策？为什么？
10. 如果真实上线，还缺什么？
```

---

## 第 15 天：开始投递

目标：

> 不再继续等项目完美，开始进入市场反馈。

任务：

```text
更新简历
整理 GitHub
补 README 示例
开始投递
记录 JD 要求
根据 JD 调整简历描述
```

投递关键词：

```text
Agent 开发工程师
LLM 应用开发工程师
AI 应用后端工程师
RAG 工程师
大模型应用开发
智能体应用开发
AI Workflow 工程师
LangChain / LangGraph 开发
```

---

# 13. 每天时间安排

## 工作日 3 小时

### 午间 1 小时

只做轻任务：

```text
写 README
写 eval case
整理接口
看必要文档
准备面试答案
补注释
```

### 晚上 2 小时

只做开发：

```text
RAG
Tool
LangGraph
权限
Trace
Eval runner
```

原则：

> 晚上不要刷教程。打开 IDE，直接写代码。

## 周末 8 小时

周末只做集成：

```text
上午：打通 RAG + Tool + Workflow
下午：补权限、trace、fallback
晚上：补 eval、README、简历
```

原则：

> 周末看教程不能超过 1 小时。

---

# 14. 最低可投递标准

第 15 天只要满足下面 6 条，就开始投递：

```text
[x] /chat 可跑         ✅ POST /api/chat/stream (SSE)
[x] RAG 可检索          ✅ pgvector + 权限过滤
[x] 3 个工具可调用       ✅ query_employee_profile / query_reimbursement_limit / create_it_ticket
[x] 权限校验存在         ✅ ToolRegistry.execute 内置 + 角色三级权限
[x] trace 可查看         ✅ audit_logs 表 + POST /api/eval/run
[x] README + 简历描述完成 ✅ README 含工具调用 + 评测
```

如果 eval 没做到 20 条，也可以先投。  
但至少要有 10 条基础 eval cases。

---

# 15. 止损规则

## 第 3 天止损

如果 FastAPI + LangGraph 还没跑通：

```text
停止看 RAG、停止看 HelloAgents。
先让 /chat 返回完整 workflow trace。
```

## 第 5 天止损

如果 pgvector 卡住：

```text
换 Chroma / FAISS / 内存检索。
先让 RAG 主流程跑通。
```

## 第 7 天止损

如果 RAG + Tool Calling 没串通：

```text
砍 Redis、并发、Streaming、LangSmith、demo 视频。
只保主流程。
```

## 第 10 天止损

如果权限和 trace 还没完成：

```text
eval 降到 10 条。
但权限、trace、fallback 必须保留。
```

## 第 15 天止损

如果项目还有小问题，但主流程可跑：

```text
开始投递。
投递后继续补。
```

---

# 16. 你应该怎么讲这个项目

面试时不要说：

> 我做了一个基于 LangGraph 的 RAG Agent。

这太弱。

你要说：

> 我做的是一个企业内部知识与流程执行 Agent。它不是单纯问答系统，而是把用户请求拆成意图识别、知识检索、工具决策、权限校验、工具执行、答案生成和 trace 记录几个状态节点。
> 
> RAG 负责回答制度类问题，Tool Calling 负责查询员工信息、报销额度和创建工单，权限模块控制工具是否允许执行，trace 和 audit log 用于失败排查和审计，eval cases 用于回归测试。
> 
> 我重点解决的是 Agent 工程化问题：模型不能直接绕过权限执行工具，工具失败要降级，回答要有引用，流程要能追踪，改 prompt 后要能通过 eval 检查是否回退。

---

# 17. 最终判断

你现在不需要再比较项目方向。

最终路线就是：

> **Enterprise Workflow Agent：RAG + Tool Calling + LangGraph Workflow + 权限审计 + Trace + Eval。**

它的定位不是最低级 Agent Demo，而是一个 **L2 入门级生产化 Agent 项目**。

15 天内不要追求大而全。  
你要追求的是：

> **小系统，闭环完整，工程意识强，面试能讲清楚。**