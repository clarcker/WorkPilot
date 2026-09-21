# WorkPilot v2 — API 接口文档

**基础 URL（开发）**：`http://localhost:8000`  
**交互式 Swagger**：`http://localhost:8000/docs`（FastAPI 自动生成，可在线调试，始终与代码同步）  
**鉴权方式**：除登录接口外，所有接口需携带 `Authorization: Bearer <access_token>`

> **快速参考优先用 Swagger UI**（`/docs`），本文档侧重业务规则、错误码、测试流程说明。

---

## 目录

1. [通用约定](#1-通用约定)
2. [认证模块 `/api/auth`](#2-认证模块-apiauth)
3. [部门管理 `/api/admin/departments`](#3-部门管理-apiadmindepartments)
4. [用户管理 `/api/admin/users`](#4-用户管理-apiadminusers)
5. [文档管理 `/api/docs`](#5-文档管理-apidocs)
6. [对话聊天 `/api/chat`](#6-对话聊天-apichat)
7. [接口总览](#7-接口总览)
8. [错误码速查](#8-错误码速查)
9. [审计日志 action 枚举](#9-审计日志-action-枚举)
10. [测试建议](#10-测试建议)

---

## 1. 通用约定

### 统一响应结构

```jsonc
// 成功
{ "code": 0, "data": { ... }, "message": "ok" }

// 失败
{ "code": 40001, "data": null, "message": "账号或密码错误" }
```

### 权限标记（本文档使用）

| 标记 | 含义 |
|---|---|
| `[公开]` | 无需登录 |
| `[登录]` | 任意已登录用户（employee / dept_admin / super_admin） |
| `[管理员]` | dept_admin 或 super_admin |
| `[超管]` | 仅 super_admin |

### 分页参数（所有列表接口通用）

Query 参数：`page`（默认 1）、`page_size`（默认 20，最大 100）

分页响应结构：
```json
{ "items": [...], "total": 100, "page": 1, "page_size": 20 }
```

### 角色权限说明

| 角色 | 说明 |
|---|---|
| `super_admin` | 全局所有权限，系统唯一 |
| `dept_admin` | 仅能管理本部门的用户和文档 |
| `employee` | 仅能使用聊天功能和修改个人信息 |

> 权限校验在服务端执行，越权请求返回 `403`。

---

## 2. 认证模块 `/api/auth`

### 2.1 登录 `[公开]`

```
POST /api/auth/login
Content-Type: application/json
```

**请求体**

```json
{ "username": "zhangsan", "password": "Admin@123456" }
```

**响应** `200`

```jsonc
{
  "code": 0,
  "data": {
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 28800,            // Token 有效期（秒），默认 8 小时 = 28800
    "must_change_password": false,  // true 时前端必须强制跳转改密页
    "user": {
      "id": 1,
      "username": "zhangsan",
      "display_name": "张三",
      "real_name": "张三",
      "role": "employee",           // super_admin / dept_admin / employee
      "dept_id": 2,
      "dept_name": "研发部",
      "dept_code": "RD"
    }
  },
  "message": "ok"
}
```

**失败**

| HTTP | code | 原因 |
|---|---|---|
| 401 | 40001 | 账号或密码错误 |
| 403 | 40002 | 账号已锁定（连续失败 ≥ 5 次，需管理员解锁） |
| 403 | 40003 | 账号已禁用 |

---

### 2.2 登出 `[登录]`

```
POST /api/auth/logout
```

将当前 Token 加入黑名单，立即失效。

**响应** `200`：`{ "code": 0, "data": null, "message": "ok" }`

---

### 2.3 刷新 Token `[登录]`

```
POST /api/auth/refresh
```

吊销旧 Token，签发新 Token。响应结构与登录相同（`LoginData`）。

---

### 2.4 修改密码 `[登录]`

```
POST /api/auth/change-password
```

> 此接口**允许 `must_change_password=true` 的用户访问**（其他业务接口对这类用户返回 403）。

**请求体**

```json
{ "old_password": "旧密码", "new_password": "新密码（至少8位）" }
```

| 场景 | old_password |
|---|---|
| 首次强制改密（`must_change_password=true`） | 可不传 |
| 普通改密 | 必须传，且正确 |

改密成功后当前 Token 自动吊销，需重新登录。

**失败**

| HTTP | code | 原因 |
|---|---|---|
| 400 | 40001 | 当前密码错误 |
| 400 | 42200 | 新密码与当前密码相同 |
| 422 | 42200 | 普通改密场景未传旧密码 |

---

### 2.5 获取当前用户信息 `[登录]`

```
GET /api/auth/me
```

**响应** `200`

```json
{
  "code": 0,
  "data": {
    "id": 1,
    "username": "zhangsan",
    "employee_no": "RD001",
    "display_name": "张三",
    "real_name": "张三",
    "role": "employee",
    "dept_id": 2,
    "dept_name": "研发部",
    "dept_code": "RD",
    "email": "zhangsan@company.com",
    "must_change_password": false,
    "last_login_at": "2026-06-01T10:00:00Z"
  },
  "message": "ok"
}
```

---

### 2.6 修改昵称 `[登录]`

```
PATCH /api/auth/me
```

**请求体**：`{ "display_name": "新昵称" }`

仅修改 `display_name`（昵称），`username` 和 `real_name` 不可通过此接口修改。

---

## 3. 部门管理 `/api/admin/departments`

> 全部接口仅 `[超管]` 可访问。

### 3.1 列出所有部门

```
GET /api/admin/departments/
```

> ⚠️ 注意尾部斜杠（FastAPI 路由规范，少了会 307 跳转）

**响应** `200`

```json
{
  "code": 0,
  "data": [
    { "id": 1, "dept_code": "HR", "dept_name": "人力资源部", "user_count": 5, "created_at": "..." }
  ],
  "message": "ok"
}
```

---

### 3.2 新建部门

```
POST /api/admin/departments/
```

**请求体**

```json
{ "dept_code": "RD", "dept_name": "研发部" }
```

`dept_code` 唯一，自动转大写（如 `rd` → `RD`）。

**响应** `201` — 返回新建的部门对象

**失败**：`409 / 40900` dept_code 已存在

---

### 3.3 修改部门名称

```
PATCH /api/admin/departments/{dept_id}
```

**请求体**：`{ "dept_name": "新名称" }`（`dept_code` 不可修改）

---

### 3.4 删除部门

```
DELETE /api/admin/departments/{dept_id}
```

**前置条件**：部门下无用户且无文档，否则返回 `409`。

---

## 4. 用户管理 `/api/admin/users`

> `[超管]` 可管理所有用户；`[管理员]` 只能管理本部门普通员工。

### 4.1 列出用户 `[管理员]`

```
GET /api/admin/users/
```

**Query 参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `dept_id` | int | 按部门过滤（仅超管有效；dept_admin 自动限制本部门） |
| `role` | string | `employee` / `dept_admin` / `super_admin` |
| `keyword` | string | 模糊搜索姓名/用户名/员工编号 |
| `is_active` | bool | `true`/`false` 过滤状态 |

**响应** `200` — 分页 `UserOut`

```jsonc
{
  "id": 5, "username": "lisi", "employee_no": "RD002",
  "display_name": "李四", "real_name": "李四",
  "role": "employee", "dept_id": 2, "dept_name": "研发部", "dept_code": "RD",
  "email": null, "is_active": true,
  "locked_at": null,            // 非 null 表示被锁定
  "failed_login_count": 0,
  "must_change_password": true,
  "last_login_at": null,
  "created_at": "2026-06-01T00:00:00Z",
  "notes": null
}
```

---

### 4.2 建议用户名 `[管理员]`

```
GET /api/admin/users/suggest-username?name=张三
```

根据真实姓名生成拼音用户名，自动检查唯一性（重名追加序号）。

**响应** `200`

```json
{ "code": 0, "data": { "suggested": "zhangsan", "pinyin_base": "zhangsan" } }
```

若 `zhangsan` 已存在则返回 `zhangsan01`，以此类推。

---

### 4.3 建议员工编号 `[管理员]`

```
GET /api/admin/users/suggest-employee-no?dept_id=2
```

**响应** `200`

```json
{ "code": 0, "data": { "suggested": "RD023", "dept_code": "RD", "next_seq": 23 } }
```

---

### 4.4 创建用户 `[管理员]`

```
POST /api/admin/users/
```

**请求体**

```json
{
  "username": "lisi",
  "employee_no": "RD002",
  "real_name": "李四",
  "role": "employee",
  "dept_id": 2,
  "email": "lisi@company.com",
  "notes": "备注（可选）"
}
```

**权限限制**：dept_admin 只能创建本部门 `employee`，不可创建 `dept_admin`；任何人都不可创建 `super_admin`。

**响应** `201`

```jsonc
{
  "code": 0,
  "data": {
    // ...UserOut 全部字段...
    "init_password": "Xk3#mP9q"  // 随机初始密码，仅此处返回一次，需转告用户
  }
}
```

新用户首次登录时 `must_change_password=true`，必须改密后才能使用其他功能。

**失败**

| HTTP | code | 原因 |
|---|---|---|
| 409 | 40900 | 用户名或员工编号已存在 |
| 400 | 40300 | 尝试创建 super_admin |
| 403 | 40301 | dept_admin 尝试创建非本部门或非 employee 角色 |

---

### 4.5 用户详情 `[管理员]`

```
GET /api/admin/users/{user_id}
```

返回 `UserOut`（同 4.1 列表中单条）。

---

### 4.6 修改用户信息 `[管理员]`

```
PATCH /api/admin/users/{user_id}
```

**请求体**（所有字段可选，传哪个改哪个）

```json
{ "display_name": "新昵称", "email": "new@example.com", "notes": "备注", "dept_id": 3, "role": "dept_admin" }
```

**权限限制**

| 操作者 | 可修改字段 |
|---|---|
| super_admin | 全部（但不可将人提升为 super_admin；不可改自己的角色） |
| dept_admin | 仅 `display_name`、`email`、`notes` |

---

### 4.7 重置密码 `[管理员]`

```
POST /api/admin/users/{user_id}/reset-password
```

生成随机新密码，设置 `must_change_password=true`。不可重置自己的密码。

**响应** `200`

```json
{ "code": 0, "data": { "new_password": "Qw7#nL2z", "must_change_password": true } }
```

---

### 4.8 启用 / 禁用账号 `[管理员]`

```
PATCH /api/admin/users/{user_id}/status
```

**请求体**：`{ "is_active": false }`（`false` 禁用，`true` 启用）

不可操作自己的账号。

---

### 4.9 解锁账号 `[管理员]`

```
POST /api/admin/users/{user_id}/unlock
```

清除锁定状态（`locked_at=null`）和失败计数（`failed_login_count=0`）。

---

### 4.10 强制登出 `[超管]`

```
POST /api/admin/users/{user_id}/force-logout
```

使该用户当前所有 Token 立即失效（时间戳水位线机制）。

---

## 5. 文档管理 `/api/docs`

> `[超管]` 管理所有部门文档；`[管理员]` 只能管理本部门文档；`employee` 无权访问。

### 5.1 上传文档 `[管理员]`

```
POST /api/docs/upload
Content-Type: multipart/form-data
```

**Form 字段**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | File | ✅ | 支持 `.pdf` / `.docx` / `.md`，最大 200 MB（可通过环境变量 `MAX_FILE_SIZE_MB` 调整） |
| `dept_id` | int | 超管必填 | 目标部门；dept_admin 自动取本部门 |
| `visibility` | string | 否 | 默认 `dept_only`，见下表 |
| `category` | string | 否 | 自定义分类标签 |
| `version` | string | 否 | 版本号（如 `v1.2`） |
| `lifecycle` | string | 否 | 默认 `effective`；可传 `draft`（草案，仅管理员召回） |
| `effective_date` | string | 否 | `YYYY-MM-DD` 生效日期 |
| `supersedes_doc_id` | int | 否 | 作为新版本替代的旧文档 ID；提交后旧文档自动 `lifecycle=superseded` |

**visibility 可选值**

| 值 | 可检索范围 |
|---|---|
| `global` | 所有登录用户 |
| `non_customer` | 非客服部门的所有成员 |
| `dept_only` | 仅本部门成员 |
| `specific_users` | 仅白名单内的指定人员（需配合 5.7/5.8 接口设置） |

**lifecycle 可选值（业务生命周期，与 status 正交）**

| 值 | 默认检索 | 说明 |
|---|---|---|
| `effective` | ✅ 所有角色 | 现行有效 |
| `superseded` | ❌ | 已被新版替代；`time_scope=historical` 时员工/管理员可见 |
| `draft` | ❌ 员工不可见 | 仅 `dept_admin` / `super_admin` 召回；员工提问不透露存在 |

**响应** `201`（上传成功，后台异步处理）

```jsonc
{
  "code": 0,
  "data": {
    "id": 10, "file_uuid": "550e...", "file_name": "入职手册.pdf",
    "file_size": 204800, "file_type": "pdf",
    "dept_id": 2, "dept_name": "研发部",
    "visibility": "dept_only",
    "status": "processing",    // 上传后立即进入后台处理
    "lifecycle": "effective",
    "effective_date": "2026-01-01",
    "supersedes_doc_id": 3,
    "supersedes_name": "旧版手册.pdf",
    "error_message": null,
    "category": null, "version": null,
    "uploaded_by": 1, "uploaded_by_name": "管理员",
    "created_at": "...", "updated_at": "...",
    "chunk_count": null        // 处理完成后才有值
  },
  "message": "文件上传成功，正在后台处理"
}
```

**文档 status 状态机**

```
processing  →  ready     （解析 + 向量化成功，可被检索）
            →  failed    （出错，error_message 有描述）
ready / failed  →  archived  （归档 / 软删除，从检索结果消失）
```

**文档 lifecycle（业务生命周期）**

```
effective  ⇄  superseded  ⇄  draft
上传替代：新文档 supersedes_doc_id=旧文档 → 旧文档自动 superseded
```

---

### 5.2 列出文档 `[管理员]`

```
GET /api/docs/
```

**Query 参数**

| 参数 | 说明 |
|---|---|
| `dept_id` | 按部门过滤（仅超管有效） |
| `status` | `processing` / `ready` / `failed` |
| `lifecycle` | `effective` / `superseded` / `draft` |
| `keyword` | 按文件名模糊搜索 |

默认不返回 `archived` 文档。

---

### 5.3 文档详情 `[管理员]`

```
GET /api/docs/{doc_id}
```

返回 `DocOut`，含 `chunk_count`（处理完成后非零）、`lifecycle`、`effective_date`、`supersedes_name`、`superseded_by_name`。

---

### 5.3b 版本链 `[管理员]`

```
GET /api/docs/{doc_id}/version-chain
```

返回旧版 → 当前 → 新版列表，每项含 `id / file_name / lifecycle / effective_date / status / is_self`。

---

### 5.4 修改文档元数据 `[管理员]`

```
PATCH /api/docs/{doc_id}
```

**请求体**（字段均可选）

```json
{
  "visibility": "global",
  "category": "制度文件",
  "version": "v2.0",
  "lifecycle": "superseded",
  "effective_date": "2026-01-01"
}
```

生命周期变更写入 `audit_logs`（action=`doc.lifecycle_update`）。已归档文档不可修改。

---

### 5.5 归档文档（软删除）`[管理员]`

```
DELETE /api/docs/{doc_id}
```

将 `status` 设为 `archived`，文档从检索中消失，数据保留。

---

### 5.6 重新索引 `[管理员]`

```
POST /api/docs/{doc_id}/reindex
```

对 `ready` 或 `failed` 状态文档重新触发解析 + 向量化。`processing` 中时返回 `409`。

---

### 5.7 查看指定人员白名单 `[管理员]`

```
GET /api/docs/{doc_id}/permissions
```

仅对 `visibility=specific_users` 的文档有意义。

**响应** `200`

```json
{
  "code": 0,
  "data": [
    { "user_id": 5, "username": "lisi", "real_name": "李四", "employee_no": "RD002", "granted_at": "..." }
  ]
}
```

---

### 5.8 替换指定人员白名单 `[管理员]`

```
PUT /api/docs/{doc_id}/permissions
```

**请求体**：`{ "user_ids": [5, 8, 12] }`

**全量替换**，传 `[]` 则清空白名单。

---

## 6. 对话聊天 `/api/chat`

> `[登录]` 用户均可访问（`must_change_password=true` 的用户被拦截，返回 `403`）。

### 6.1 流式问答（核心接口）`[登录]`

```
POST /api/chat/stream
Content-Type: application/json
```

**请求体**

```json
{ "query": "公司的年假政策是什么？", "conversation_id": null }
```

| 字段 | 说明 |
|---|---|
| `query` | 用户问题，不可为空，最大 4000 字符 |
| `conversation_id` | `null` 新建会话；传已有 ID 则追加到该会话 |

**响应**：`Content-Type: text/event-stream`，每行格式 `data: <JSON>\n\n`

**SSE 事件类型（按出现顺序）**

| type | content 类型 | 说明 |
|---|---|---|
| `conversation_id` | **number**（整数） | 新建会话时第一条，客户端须保存用于后续追问 |
| `token` | string | 流式 token，依次拼接为完整回答 |
| `sources` | array | 检索到相关文档时出现，结构见下 |
| `tool_call` | object | 工具调用结果（含 `requires_confirmation` / `missing_slots`） |
| `confirm_required` | object | 写操作生成草稿，需用户确认；见下 |
| `form_incomplete` | object | 槽位缺失：`{missing_slots, message}` |
| `done` | string（空） | 流结束标志，最后一条 |
| `error` | string | 异常描述，之后紧跟 `done` |

**confirm_required content**

```jsonc
{
  "tool_name": "submit_reimbursement_request",
  "payload": {
    "request_id": 1,
    "request_no": "RB-20260916-0001",
    "status": "draft",
    "requires_confirmation": true,
    "form": { "category": "差旅住宿", "amount": 1800, "days": 3, "trip_start": "...", "trip_end": "...", "approval_ref": "TR-..." },
    "precheck": { "ok": true, "remaining": 37700, "requires_special_approval": true, "violations": [...] }
  }
}
```

确认 / 取消：
- `POST /api/reimbursements/{request_id}/confirm` → `pending`，占用年度额度
- `POST /api/reimbursements/{request_id}/cancel` → `cancelled`，不产生审批记录

**sources 单项结构**

```jsonc
{
  "doc_id":   10,
  "doc_name": "入职手册.pdf",    // 文档文件名
  "chunk_id": 42,               // 分块 ID
  "heading":  "第三章 年假制度", // 所在章节标题（可为 null）
  "page_no":  8,                // 所在页码（可为 null）
  "score":    0.87              // 余弦相似度，0-1，越高越相关
}
```

**完整 SSE 示例**

```
data: {"type": "conversation_id", "content": 42}

data: {"type": "token", "content": "公司年假"}
data: {"type": "token", "content": "政策如下："}

data: {"type": "sources", "content": [{"doc_id": 10, "doc_name": "入职手册.pdf", "chunk_id": 42, "heading": "第三章 年假制度", "page_no": 8, "score": 0.87}]}

data: {"type": "tool_call", "content": {"tool_name": "submit_reimbursement_request", "tool_args": {"category": "差旅住宿", "amount": 1800}, "allowed": true, "result": {"request_id": 1, "request_no": "RB-20260916-0001", "status": "draft"}, "requires_confirmation": true, "latency_ms": 12}}

data: {"type": "confirm_required", "content": {"tool_name": "submit_reimbursement_request", "payload": {"request_id": 1, "request_no": "RB-20260916-0001", "form": {"category": "差旅住宿", "amount": 1800, "days": 3}, "precheck": {"ok": true, "requires_special_approval": true, "violations": [{"rule": "daily_max", "message": "住宿日均 600 元，超出标准 500 元/天，超标 300 元"}]}}}}

data: {"type": "done", "content": ""}
```

> ⚠️ 浏览器原生 `EventSource` 不支持 POST，需用 `fetch` + `ReadableStream` 手动解析 SSE。

---

### 6.2 列出会话 `[登录]`

```
GET /api/chat/conversations
```

仅返回当前用户自己的活跃会话，按 `updated_at` 倒序。

**响应** `200` — 分页

```json
{
  "id": 42, "title": "公司的年假政策是什么", "status": "active",
  "message_count": 4, "created_at": "...", "updated_at": "..."
}
```

---

### 6.3 获取会话详情（含消息）`[登录]`

```
GET /api/chat/conversations/{conv_id}
```

**响应** `200`

```jsonc
{
  "code": 0,
  "data": {
    "conversation": { "id": 42, "title": "...", "status": "active", "message_count": 4, ... },
    "messages": [
      {
        "id": 1, "role": "user",
        "content": "公司的年假政策是什么？",
        "sources": null, "created_at": "..."
      },
      {
        "id": 2, "role": "assistant",
        "content": "公司年假政策如下...",
        "sources": [
          { "doc_id": 10, "doc_name": "入职手册.pdf", "chunk_id": 42, "heading": "第三章 年假制度", "page_no": 8, "score": 0.87 }
        ],
        "created_at": "..."
      }
    ]
  }
}
```

---

### 6.4 删除会话 `[登录]`

```
DELETE /api/chat/conversations/{conv_id}
```

软删除（`status → archived`），用户只能删自己的会话。

---

## 7. 接口总览

| 模块 | 数量 | 路由前缀 | 最低权限 |
|---|---|---|---|
| 认证 | 6 | `/api/auth` | 公开（登录除外） |
| 部门管理 | 4 | `/api/admin/departments` | 超管 |
| 用户管理 | 10 | `/api/admin/users` | 管理员 |
| 文档管理 | 8 | `/api/docs` | 管理员 |
| 对话聊天 | 4 | `/api/chat` | 登录 |
| 健康检查 | 1 | `/health` | 公开 |
| **合计** | **33** | — | — |

> **Phase 2 待实现**：审计日志查询 `/api/admin/audit`、系统配置 `/api/admin/system`。

---

## 7b. 报销申请 `/api/reimbursements`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| POST | `/{id}/confirm` | `[登录]` | 确认草稿 → pending，占用额度 |
| POST | `/{id}/cancel` | `[登录]` | 取消 draft/pending，退回额度 |
| GET | `/mine` | `[登录]` | 我的申请列表 |
| GET | `/approvals` | `[管理员]` | 审批队列（部门管理员仅本部门） |
| POST | `/{id}/decision` | `[管理员]` | `{"approved": bool, "comment": "..."}` |

## 7c. Agent Trace `/api/admin/traces`

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/` | `[管理员]` | 分页列表；部门管理员仅本部门 |
| GET | `/{id}` | `[管理员]` | 节点步骤、工具、回答详情 |

---

## 8. 错误码速查

| HTTP | code | 含义 |
|---|---|---|
| 400 | 40001 | 账号或密码错误 / 旧密码错误 |
| 400 | 40300 | 操作被拒绝（如创建 super_admin、禁用自己） |
| 401 | 401 | Token 未携带或已失效 |
| 401 | 40101 | Token 无效或已吊销 |
| 403 | 40002 | 账号已锁定 |
| 403 | 40003 | 账号已禁用 |
| 403 | 40301 | 跨部门 / 跨角色权限不足 |
| 404 | 40400 | 资源不存在 |
| 409 | 40900 | 唯一性冲突（用户名 / 员工编号 / 部门代码重复） |
| 409 | 40901 | 部门下还有用户，无法删除 |
| 409 | 40902 | 部门下还有文档，无法删除 |
| 413 | 41300 | 上传文件超过大小限制（默认 200 MB） |
| 422 | 42200 | 参数格式或业务规则校验失败 |
| 500 | 50001 | 服务器内部错误 |

---

## 9. 审计日志 action 枚举

以下操作会自动写入 `audit_logs` 表（不可删除），供后续审计查询接口使用。

| action | 触发场景 |
|---|---|
| `auth.login` | 用户登录（含失败） |
| `auth.logout` | 主动登出 |
| `auth.change_password` | 修改密码 |
| `user.create` | 创建用户 |
| `user.update` | 修改用户信息 |
| `user.reset_password` | 重置密码 |
| `user.enable` | 启用账号 |
| `user.disable` | 禁用账号 |
| `user.unlock` | 解锁账号 |
| `user.force_logout` | 强制登出 |
| `dept.create` | 创建部门 |
| `dept.update` | 修改部门 |
| `dept.delete` | 删除部门 |
| `doc.upload` | 上传文档 |
| `doc.update` | 修改文档元数据 |
| `doc.archive` | 归档文档 |
| `doc.permission_update` | 修改文档白名单 |

---

## 10. 测试建议

### 初始超级管理员

| 字段 | 值 |
|---|---|
| 用户名 | `admin` |
| 初始密码 | `Admin@123`（种子脚本默认值） |
| 首次登录 | 强制改密（`must_change_password=true`） |

> 当前环境已改密为 `Admin@456!`

### 推荐测试顺序

```
1.  admin 登录  →  收到 must_change_password=true  →  调用改密接口  →  重新登录
2.  创建部门（如 HR、RD）
3.  创建部门管理员账号（hrmanager、rdmanager）
4.  各自登录部门管理员，创建普通员工账号（验证初始密码只返回一次）
5.  普通员工首次登录  →  强制改密流程
6.  普通员工尝试调用文档上传  →  应返回 403（权限隔离）
7.  部门管理员上传文档，轮询文档详情直到 status=ready
8.  普通员工发起聊天，验证 SSE 流事件顺序：
      conversation_id（number） → token × N → sources → done
9.  验证跨部门文档隔离：visibility=dept_only 时另一部门员工检索不到该文档
10. 连续登录失败 5 次  →  账号锁定  →  管理员解锁  →  正常登录
```

### 健康检查

```
GET /health
```

无需认证，返回 `{ "status": "ok" }`，可用于 Docker 探针。

### 快速调试工具

- **Swagger UI**（推荐）：`http://localhost:8000/docs` — 在线直接调用，自动带 token
- **ReDoc**：`http://localhost:8000/redoc` — 更适合阅读

---

## 附：API 文档维护说明

| 内容 | 维护方式 |
|---|---|
| 接口字段、类型、HTTP 方法 | 以 `/docs` Swagger 为准（代码改了自动同步） |
| 业务规则、错误码、权限说明 | 本文档手动维护，**接口改动时同步更新本文档** |
| 测试流程 | 本文档维护 |

**原则**：代码改动 → 同一个 commit 里同步更新本文件对应章节，保证文档永远不落后于代码。
