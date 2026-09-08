# WorkPilot v2 需求文档

## 数据库模型

### 2026-06-25 新增：工具调用记录表 (tool_calls)

**功能描述：**
记录系统中所有工具调用的详细信息，用于审计、调试和性能分析。

**字段说明：**
- `id`: 主键，BIGSERIAL
- `conversation_id`: 关联的会话ID（可为空，SET NULL）
- `message_id`: 关联的消息ID（可为空，SET NULL）
- `user_id`: 调用工具的用户ID
- `tool_name`: 工具名称（最大100字符）
- `tool_args`: 工具调用参数（JSONB格式）
- `tool_result`: 工具返回结果（JSONB格式，可为空）
- `allowed`: 是否允许调用（布尔值，默认true）
- `deny_reason`: 拒绝原因（文本，可为空）
- `latency_ms`: 调用延迟（毫秒，可为空）
- `error`: 错误信息（文本，可为空）
- `idempotency_key`: 幂等键（最大255字符，唯一，可为空）
- `created_at`: 创建时间（带时区）

**索引：**
- `idx_tool_calls_user_id`: 用户ID索引
- `idx_tool_calls_tool_name`: 工具名称索引
- `idx_tool_calls_created_at`: 创建时间索引

### 2026-06-25 新增：IT工单表 (it_tickets)

**功能描述：**
存储IT支持工单信息，用于`create_it_ticket`工具创建的工单管理。

**字段说明：**
- `id`: 主键，BIGSERIAL
- `ticket_no`: 工单编号（最大50字符，唯一）
- `user_id`: 创建工单的用户ID
- `issue_type`: 问题类型（最大100字符）
- `description`: 问题描述（文本）
- `status`: 工单状态（最大20字符，默认"open"）
- `idempotency_key`: 幂等键（最大255字符，唯一）
- `created_at`: 创建时间（带时区）
- `updated_at`: 更新时间（带时区，自动更新）

**索引：**
- `idx_it_tickets_user_id`: 用户ID索引
- `idx_it_tickets_status`: 状态索引

## 工具调用基础设施

### 2026-06-25 新增：工具基座模块 (`backend/tools/base.py`)

**功能描述：**
为 WorkPilot 的工具调用系统提供基础设施，包括工具注册、权限控制、参数校验和执行框架。

**核心组件：**

1. **ToolContext** — 工具执行上下文，携带用户信息：
   - `user_id`、`user_role`、`user_dept_id`（可选）、`conversation_id`（可选）、`message_id`（可选）

2. **ToolResult** — 工具执行结果：
   - `success`、`data`、`error`（可选）、`deny_reason`（权限拒绝时）

3. **ToolDef** — 工具定义：
   - `name`、`description`、`func`、`permissions`（空列表=所有角色可用）、`params_schema`（JSON Schema）、`is_idempotent`

4. **ToolRegistry** — 工具注册中心：
   - `register()`：注册工具，重复名称抛 ValueError
   - `get()`：按名称查找
   - `list_tools()`：列出所有工具
   - `get_tools_for_prompt(role)`：按角色过滤，返回 LLM 友好格式
   - `execute(name, args, ctx)`：带权限校验、参数校验、类型强制转换的执行

5. **@tool 装饰器** — 自动从函数签名生成 JSON Schema 并注册到全局 registry

6. **make_idempotency_key()** — 基于 SHA256 的幂等键生成

**权限规则：**
- `permissions` 为空列表时，所有角色均可使用
- `permissions` 非空时，仅列表中的角色可使用
- 权限不足时返回 `deny_reason`

**参数校验：**
- 自动从类型注解生成 JSON Schema
- 执行时校验 required 参数
- 自动进行整数类型强制转换

## LangGraph 工作流集成

### 2026-06-25 新增：工具调用节点与状态字段

**功能描述：**
将工具调用能力集成到 RAG 工作流中，在检索完成后、生成回答前，由 LLM 判断是否需要调用工具，如需要则执行工具并将结果注入回答上下文。

**修改内容：**

1. **RAGState 新增字段** (`graph/state.py`)：
   - `need_tool: bool` — 是否需要调用工具
   - `tool_name: Optional[str]` — LLM 选择的工具名
   - `tool_args: dict` — LLM 生成的工具参数
   - `tool_result: Optional[dict]` — 工具执行结果
   - `permission_denied: Optional[str]` — 权限拒绝原因
   - `trace: list[dict]` — 每个节点的执行追踪

2. **新增节点** (`graph/nodes.py`)：
   - `decide_tool_node` — 工具决策节点，调用 LLM 判断是否需要工具
   - `execute_tool_node` — 工具执行节点，调用工具并通过 SSE 推送 `tool_call` 事件
   - `route_after_decide_tool` — 路由函数：需要工具→执行；不需要→直接生成回答

3. **工作流变更** (`graph/workflow.py`)：
   - 原路径：`retrieve_docs → generate_answer`
   - 新路径：`retrieve_docs → decide_tool → [execute_tool →] generate_answer`
   - 闲聊路径不变

4. **Chat API 更新** (`api/chat.py`)：
   - 初始状态包含所有新字段
   - 流水线完成后记录工具调用审计日志（`TOOL_CALL` / `TOOL_DENY`）

**SSE 新事件类型：**
- `{"type": "tool_call", "content": {"tool_name", "tool_args", "allowed", "deny_reason", "result", "error", "latency_ms"}}`

## 影响范围

- 新增两个数据库表
- 新增Alembic迁移文件：`backend/alembic/versions/0002_add_tool_tables.py`
- 更新数据库模型文件：`backend/db/models.py`
- 修改 `graph/state.py`：RAGState 新增 6 个工具相关字段
- 修改 `graph/nodes.py`：新增 2 个节点 + 1 个路由函数
- 修改 `graph/workflow.py`：工作流新增工具决策和执行路径
- 修改 `api/chat.py`：初始状态更新 + 审计日志

## 边界条件

- `tool_calls`表的`conversation_id`和`message_id`为可选字段，允许独立记录工具调用
- `it_tickets`表的`idempotency_key`为必填字段，确保工单唯一性
- 所有时间字段使用带时区的TIMESTAMPTZ类型