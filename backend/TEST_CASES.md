# WorkPilot v2 后端测试用例详细清单

**文档版本：** 1.0  
**编制日期：** 2026-06-01  
**总用例数：** 130+

---

## 目录

1. [认证模块（Auth）](#认证模块)
2. [部门管理](#部门管理)
3. [用户管理](#用户管理)
4. [文档管理](#文档管理)
5. [对话聊天](#对话聊天)
6. [审计日志](#审计日志)
7. [系统配置](#系统配置)
8. [LangGraph 工作流](#langgraph-工作流)
9. [跨模块集成](#跨模块集成)

---

## 认证模块

### 1.1 登录（POST /api/auth/login）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| AUTH-001 | 正常登录 | 有效用户名和密码 | code=0, access_token, expires_in=28800, user 信息 | ⭐⭐⭐ |
| AUTH-002 | 密码错误 | 存在的用户名 + 错误密码 | code=40001, message="账号或密码错误" | ⭐⭐⭐ |
| AUTH-003 | 用户不存在 | 不存在的用户名 + 任意密码 | code=40001, message="账号或密码错误" | ⭐⭐⭐ |
| AUTH-004 | 账号被禁用 | 被禁用账号 + 正确密码 | code=40003, message="账号已禁用" | ⭐⭐⭐ |
| AUTH-005 | 账号被锁定 | 被锁定账号（失败登录超过5次） | code=40002, message="账号已锁定" | ⭐⭐⭐ |
| AUTH-006 | 需要修改密码 | 首次创建用户账号登录 | must_change_password=true，需强制跳转改密页 | ⭐⭐⭐ |
| AUTH-007 | 用户名为空 | "" | 返回 422 Unprocessable Entity | ⭐⭐ |
| AUTH-008 | 密码为空 | 用户名有效，密码为 "" | 返回 422 Unprocessable Entity | ⭐⭐ |
| AUTH-009 | 连续 5 次密码错误 | 同一账号连续尝试 5 次 | 第 5 次后账号自动锁定 | ⭐⭐⭐ |
| AUTH-010 | 登录后获取用户信息 | 成功登录后记录 JWT | 可用于后续请求头 Authorization | ⭐⭐⭐ |

### 1.2 登出（POST /api/auth/logout）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| AUTH-011 | 正常登出 | 有效 JWT | code=0, data=null | ⭐⭐⭐ |
| AUTH-012 | 无 Token 登出 | 不提供 Authorization 头 | code=40101, message="Token 无效或已过期" | ⭐⭐⭐ |
| AUTH-013 | 已吊销 Token 登出 | 已被吊销的 Token | code=40102, message="Token 已吊销（强制登出）" | ⭐⭐⭐ |
| AUTH-014 | 重复登出 | 登出后再用同一 Token 登出 | 第二次返回 40102 | ⭐⭐ |
| AUTH-015 | Token 在黑名单中 | 登出后该 Token 应在黑名单 | 用该 Token 调用其他 API 返回 40102 | ⭐⭐⭐ |

### 1.3 刷新 Token（POST /api/auth/refresh）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| AUTH-016 | 正常刷新 | 有效未过期 Token | 返回新 Token，旧 Token 吊销 | ⭐⭐⭐ |
| AUTH-017 | 已过期 Token 刷新 | 过期的 Token | code=40101, message="Token 无效或已过期" | ⭐⭐⭐ |
| AUTH-018 | 无 Token 刷新 | 不提供 Authorization 头 | code=40101 | ⭐⭐⭐ |
| AUTH-019 | 已吊销 Token 刷新 | 已登出的 Token | code=40102 | ⭐⭐⭐ |
| AUTH-020 | 刷新后旧 Token 失效 | 获得新 Token 后，立即用旧 Token 调用 API | 返回 40102 | ⭐⭐⭐ |

### 1.4 修改密码（POST /api/auth/change-password）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| AUTH-021 | 正常修改密码 | 有效 Token，正确旧密码，新密码符合要求 | code=0, 当前 Token 吊销，must_change_password=false | ⭐⭐⭐ |
| AUTH-022 | 旧密码错误 | 非首次改密，提供错误的旧密码 | code=40001, message="密码错误" | ⭐⭐⭐ |
| AUTH-023 | 首次改密（旧密码为空） | 新用户首次登录，old_password="" | 服务端跳过旧密码校验，直接修改 | ⭐⭐⭐ |
| AUTH-024 | 新密码为空 | 有效 Token，old_password 正确，new_password="" | code=422, 密码格式校验失败 | ⭐⭐ |
| AUTH-025 | 新密码与旧密码相同 | old_password="Admin@123", new_password="Admin@123" | code=400, message="新密码不能与旧密码相同" | ⭐⭐ |
| AUTH-026 | 无 Token 修改密码 | 不提供 Authorization 头 | code=40101 | ⭐⭐⭐ |
| AUTH-027 | 修改密码后强制重新登录 | 修改密码成功，用旧密码登录 | 登录失败（密码不匹配）| ⭐⭐⭐ |

### 1.5 获取当前用户信息（GET /api/auth/me）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| AUTH-028 | 正常获取用户信息 | 有效 Token | code=0, 返回 id/username/display_name/role/dept_info | ⭐⭐⭐ |
| AUTH-029 | 验证用户所有字段 | 有效 Token | 验证 employee_no、real_name、dept_code、email、last_login_at 等 | ⭐⭐⭐ |
| AUTH-030 | 无 Token 获取信息 | 不提供 Authorization 头 | code=40101 | ⭐⭐⭐ |
| AUTH-031 | 过期 Token 获取信息 | 过期的 Token | code=40101 | ⭐⭐⭐ |
| AUTH-032 | 获取信息后的数据一致性 | 登录时返回的用户信息与 /me 返回信息对比 | 两处数据应完全一致 | ⭐⭐⭐ |

### 1.6 修改个人信息（PATCH /api/auth/me）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| AUTH-033 | 正常修改昵称 | 有效 Token，display_name="张三·新昵称" | code=0, data=null | ⭐⭐⭐ |
| AUTH-034 | 修改后验证数据更新 | 修改昵称后调用 /me 接口 | display_name 应为新值 | ⭐⭐⭐ |
| AUTH-035 | 尝试修改用户名（应被拒绝） | 请求体包含 username 字段 | 服务端忽略该字段或返回错误 | ⭐⭐ |
| AUTH-036 | 尝试修改 role（应被拒绝） | 请求体包含 role 字段 | 服务端忽略该字段或返回错误 | ⭐⭐ |
| AUTH-037 | 昵称长度边界 | display_name 为空字符串 | code=422, 字段验证失败 | ⭐⭐ |
| AUTH-038 | 无 Token 修改个人信息 | 不提供 Authorization 头 | code=40101 | ⭐⭐⭐ |

---

## 部门管理

### 2.1 部门列表（GET /api/admin/departments）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DEPT-001 | 超管获取所有部门 | [超管] Token，无查询参数 | code=0, 返回所有部门列表，包含 id/dept_code/dept_name/member_count/created_at | ⭐⭐⭐ |
| DEPT-002 | 部门管理员获取部门列表 | [部门管理员] Token | code=0，应只返回当前部门信息还是全部？（需确认文档） | ⭐⭐⭐ |
| DEPT-003 | 普通员工获取部门列表 | [员工] Token | code=40301, message="无权限执行此操作" | ⭐⭐⭐ |
| DEPT-004 | 无 Token 获取部门列表 | 不提供 Authorization 头 | code=40101 | ⭐⭐⭐ |
| DEPT-005 | 部门成员数量一致性 | 创建部门，添加 N 个用户，查询 member_count | member_count 应等于 N | ⭐⭐⭐ |
| DEPT-006 | 返回数据完整性 | 正常查询 | 每个部门项都包含所有必要字段 | ⭐⭐⭐ |

### 2.2 创建部门（POST /api/admin/departments）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DEPT-007 | 超管创建部门 | [超管] Token，dept_code="IT", dept_name="信息技术部" | code=0, 返回 id/dept_code/dept_name | ⭐⭐⭐ |
| DEPT-008 | 部门管理员尝试创建部门 | [部门管理员] Token | code=40301, "无权限执行此操作" | ⭐⭐⭐ |
| DEPT-009 | 员工尝试创建部门 | [员工] Token | code=40301 | ⭐⭐⭐ |
| DEPT-010 | 重复的 dept_code | 同一 dept_code 创建两次 | 第二次返回 code=40901, "部门代码已存在"（待确认错误码） | ⭐⭐⭐ |
| DEPT-011 | dept_code 格式校验 | dept_code 包含小写字母或特殊字符 | code=422, 应为大写英文 | ⭐⭐ |
| DEPT-012 | dept_name 为空 | dept_code 有效，dept_name="" | code=422 | ⭐⭐ |
| DEPT-013 | 部门 code 为空 | dept_code=""，dept_name 有效 | code=422 | ⭐⭐ |
| DEPT-014 | 创建后验证数据库一致性 | 创建部门后查询列表 | 新部门应出现在列表中 | ⭐⭐⭐ |

### 2.3 修改部门（PUT /api/admin/departments/{dept_id}）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DEPT-015 | 超管修改部门名称 | [超管] Token，dept_id=2，dept_name="新部门名" | code=0, data=null | ⭐⭐⭐ |
| DEPT-016 | 尝试修改 dept_code | 请求体包含 dept_code 字段 | 服务端忽略或返回错误 | ⭐⭐ |
| DEPT-017 | 修改不存在的部门 | dept_id=9999 | code=40401, message="资源不存在" | ⭐⭐⭐ |
| DEPT-018 | 部门管理员修改部门 | [部门管理员] Token，修改自己部门 | code=40301，管理员无权限修改部门 | ⭐⭐⭐ |
| DEPT-019 | 修改后验证数据更新 | 修改部门名后查询详情 | dept_name 应为新值 | ⭐⭐⭐ |
| DEPT-020 | 修改为空名称 | dept_name="" | code=422 | ⭐⭐ |

### 2.4 删除部门（DELETE /api/admin/departments/{dept_id}）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DEPT-021 | 删除空部门 | [超管] Token，部门内无用户 | code=0, data=null | ⭐⭐⭐ |
| DEPT-022 | 删除有用户的部门 | 部门内有员工 | code=400, message="部门下有用户，无法删除" | ⭐⭐⭐ |
| DEPT-023 | 删除有文档的部门 | 部门内有已上传文档 | code=400, message="部门下有文档，无法删除" | ⭐⭐⭐ |
| DEPT-024 | 删除不存在的部门 | dept_id=9999 | code=40401 | ⭐⭐⭐ |
| DEPT-025 | 部门管理员删除部门 | [部门管理员] Token | code=40301 | ⭐⭐⭐ |
| DEPT-026 | 删除后验证不存在 | 删除后尝试查询该部门 | code=40401 | ⭐⭐⭐ |

---

## 用户管理

### 3.1 用户列表（GET /api/admin/users）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-001 | 超管查看所有用户 | [超管] Token，无过滤条件 | code=0, 返回分页列表，包含所有部门用户 | ⭐⭐⭐ |
| USER-002 | 部门管理员查看本部门用户 | [部门管理员] Token，不传 dept_id（默认本部门） | code=0, 仅返回本部门用户 | ⭐⭐⭐ |
| USER-003 | 部门管理员尝试查看其他部门 | [部门管理员] Token，dept_id=其他部门 | code=40301 或自动限制为本部门 | ⭐⭐⭐ |
| USER-004 | 员工查看用户列表 | [员工] Token | code=40301 | ⭐⭐⭐ |
| USER-005 | 按部门过滤 | dept_id=2 | 返回列表仅包含该部门用户 | ⭐⭐⭐ |
| USER-006 | 按角色过滤 | role="dept_admin" | 仅返回部门管理员 | ⭐⭐⭐ |
| USER-007 | 按关键词搜索 | keyword="张三" | 返回用户名或姓名包含"张三"的用户 | ⭐⭐⭐ |
| USER-008 | 按是否启用过滤 | is_active=false | 仅返回被禁用的用户 | ⭐⭐⭐ |
| USER-009 | 分页查询 | page=1, page_size=10 | 返回第1页，共10条记录，total 正确 | ⭐⭐⭐ |
| USER-010 | 组合条件查询 | dept_id=2, role="employee", is_active=true | 返回综合过滤结果 | ⭐⭐⭐ |
| USER-011 | 超出范围的分页 | page=9999, page_size=10 | 返回空列表或最后一页 | ⭐⭐ |

### 3.2 用户名推荐（GET /api/admin/users/suggest-username）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-012 | 推荐不存在的用户名 | real_name="李四" | username="lisi", is_available=true | ⭐⭐⭐ |
| USER-013 | 推荐已存在的用户名 | real_name="张三"（已存在） | username="zhangsan01", is_available=true（自动追加序号） | ⭐⭐⭐ |
| USER-014 | 多个重名用户 | 已存在 zhangsan, zhangsan01, zhangsan02 | 推荐 zhangsan03 | ⭐⭐⭐ |
| USER-015 | 权限验证 | [员工] Token 调用 | code=40301 | ⭐⭐⭐ |
| USER-016 | 无 Token 调用 | 不提供 Authorization 头 | code=40101 | ⭐⭐⭐ |

### 3.3 员工编号推荐（GET /api/admin/users/suggest-employee-no）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-017 | 推荐新部门编号 | dept_id=2（该部门最大序号为 RD002） | employee_no="RD003" | ⭐⭐⭐ |
| USER-018 | 推荐无用户部门编号 | dept_id=5（无用户） | employee_no="新部门代码001"（待确认规则） | ⭐⭐⭐ |
| USER-019 | 部门不存在 | dept_id=9999 | code=40401 | ⭐⭐⭐ |
| USER-020 | 权限验证 | [员工] Token | code=40301 | ⭐⭐⭐ |

### 3.4 创建用户（POST /api/admin/users）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-021 | 超管创建员工 | [超管] Token，real_name="李四", username="lisi", employee_no="RD002", role="employee" | code=0, 返回 id/username/temp_password/dept_name | ⭐⭐⭐ |
| USER-022 | 超管创建部门管理员 | [超管] Token，role="dept_admin" | code=0 | ⭐⭐⭐ |
| USER-023 | 部门管理员创建本部门员工 | [部门管理员] Token，dept_id=自己部门 | code=0 | ⭐⭐⭐ |
| USER-024 | 部门管理员创建其他部门员工 | [部门管理员] Token，dept_id≠自己部门 | code=40301 | ⭐⭐⭐ |
| USER-025 | 部门管理员尝试创建管理员 | [部门管理员] Token，role="dept_admin" | code=40301 | ⭐⭐⭐ |
| USER-026 | 创建时重复用户名 | username 已存在 | code=40901, "用户名已存在" | ⭐⭐⭐ |
| USER-027 | 创建时重复员工编号 | employee_no 已存在 | code=40902, "员工编号已存在" | ⭐⭐⭐ |
| USER-028 | 创建时不存在的部门 | dept_id=9999 | code=40401 | ⭐⭐⭐ |
| USER-029 | 用户创建后是否启用 | 创建后查询用户 | is_active=true（新用户默认启用） | ⭐⭐⭐ |
| USER-030 | 临时密码生成 | 查看创建响应 | temp_password 应为随机8位（需验证格式） | ⭐⭐⭐ |
| USER-031 | 临时密码仅返回一次 | 创建后再调用查看用户详情 | 无法获取 temp_password | ⭐⭐⭐ |
| USER-032 | 必填字段验证 | 缺少 real_name/username/dept_id/role | code=422 | ⭐⭐ |

### 3.5 查看用户详情（GET /api/admin/users/{user_id}）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-033 | 超管查看用户详情 | [超管] Token，user_id 任意 | code=0, 返回完整用户信息 | ⭐⭐⭐ |
| USER-034 | 部门管理员查看本部门用户 | [部门管理员] Token，user_id=本部门用户 | code=0 | ⭐⭐⭐ |
| USER-035 | 部门管理员查看其他部门用户 | [部门管理员] Token，user_id=其他部门用户 | code=40301 | ⭐⭐⭐ |
| USER-036 | 查看不存在的用户 | user_id=9999 | code=40401 | ⭐⭐⭐ |
| USER-037 | 员工查看用户详情 | [员工] Token | code=40301 | ⭐⭐⭐ |
| USER-038 | 用户查看自己的信息 | 员工查看自己（user_id=self） | 应允许还是返回40301？（需确认） | ⭐⭐ |

### 3.6 修改用户信息（PUT /api/admin/users/{user_id}）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-039 | 修改用户昵称 | [超管] Token，display_name="李四·新" | code=0 | ⭐⭐⭐ |
| USER-040 | 修改用户邮箱 | email="lisi@company.com" | code=0 | ⭐⭐⭐ |
| USER-041 | 修改用户备注 | notes="研发二组" | code=0 | ⭐⭐⭐ |
| USER-042 | 尝试修改用户名 | 请求体包含 username | 服务端忽略或返回错误 | ⭐⭐ |
| USER-043 | 尝试修改员工编号 | 请求体包含 employee_no | 服务端忽略或返回错误 | ⭐⭐ |
| USER-044 | 尝试修改角色 | 请求体包含 role="super_admin" | 服务端忽略或返回错误 | ⭐⭐ |
| USER-045 | 尝试修改部门 | 请求体包含 dept_id | 服务端忽略或返回错误 | ⭐⭐ |
| USER-046 | 部门管理员修改本部门用户 | [部门管理员] Token，user_id=本部门 | code=0 | ⭐⭐⭐ |
| USER-047 | 部门管理员修改其他部门用户 | [部门管理员] Token，user_id=其他部门 | code=40301 | ⭐⭐⭐ |
| USER-048 | 修改不存在的用户 | user_id=9999 | code=40401 | ⭐⭐⭐ |

### 3.7 重置密码（POST /api/admin/users/{user_id}/reset-password）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-049 | 超管重置用户密码 | [超管] Token，user_id 任意 | code=0, 返回 temp_password | ⭐⭐⭐ |
| USER-050 | 重置后 must_change_password 标记 | 重置密码后查询用户 | must_change_password=true | ⭐⭐⭐ |
| USER-051 | 重置后旧 Token 吊销 | 重置密码前获取 Token，重置后再用 Token 调用 API | Token 应被吊销（40102） | ⭐⭐⭐ |
| USER-052 | 部门管理员重置本部门用户 | [部门管理员] Token | code=0 | ⭐⭐⭐ |
| USER-053 | 部门管理员重置其他部门用户 | [部门管理员] Token，user_id=其他部门 | code=40301 | ⭐⭐⭐ |
| USER-054 | 重置不存在的用户 | user_id=9999 | code=40401 | ⭐⭐⭐ |
| USER-055 | 员工重置密码 | [员工] Token 调用 | code=40301 | ⭐⭐⭐ |

### 3.8 禁用用户（POST /api/admin/users/{user_id}/disable）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-056 | 超管禁用用户 | [超管] Token，user_id 任意 | code=0, data=null | ⭐⭐⭐ |
| USER-057 | 禁用后用户不能登录 | 禁用后用该用户登录 | code=40003, "账号已禁用" | ⭐⭐⭐ |
| USER-058 | 禁用时吊销所有 Token | 禁用前获取 Token，禁用后用 Token 调用 API | Token 应被吊销 | ⭐⭐⭐ |
| USER-059 | 部门管理员禁用本部门用户 | [部门管理员] Token | code=0 | ⭐⭐⭐ |
| USER-060 | 部门管理员禁用其他部门用户 | [部门管理员] Token，user_id=其他部门 | code=40301 | ⭐⭐⭐ |
| USER-061 | 禁用不存在的用户 | user_id=9999 | code=40401 | ⭐⭐⭐ |
| USER-062 | 禁用已禁用的用户 | 重复禁用 | code=0 或返回 400（待确认） | ⭐⭐ |

### 3.9 启用用户（POST /api/admin/users/{user_id}/enable）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-063 | 超管启用用户 | [超管] Token，user_id 任意 | code=0, data=null | ⭐⭐⭐ |
| USER-064 | 启用后用户可以登录 | 启用被禁用用户后登录 | 登录成功 | ⭐⭐⭐ |
| USER-065 | 部门管理员启用本部门用户 | [部门管理员] Token | code=0 | ⭐⭐⭐ |
| USER-066 | 部门管理员启用其他部门用户 | [部门管理员] Token，user_id=其他部门 | code=40301 | ⭐⭐⭐ |
| USER-067 | 启用已启用的用户 | 重复启用 | code=0 或返回 400 | ⭐⭐ |

### 3.10 解锁用户（POST /api/admin/users/{user_id}/unlock）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-068 | 超管解锁用户 | [超管] Token，被锁定用户 ID | code=0 | ⭐⭐⭐ |
| USER-069 | 解锁后用户可以登录 | 解锁后用该用户登录 | 登录成功 | ⭐⭐⭐ |
| USER-070 | 解锁后失败计数清零 | 解锁后再次失败登录 | failed_login_count 从1开始，不会立即锁定 | ⭐⭐⭐ |
| USER-071 | 部门管理员解锁本部门用户 | [部门管理员] Token | code=0 | ⭐⭐⭐ |
| USER-072 | 部门管理员解锁其他部门用户 | [部门管理员] Token，user_id=其他部门 | code=40301 | ⭐⭐⭐ |

### 3.11 强制登出（POST /api/admin/users/{user_id}/force-logout）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| USER-073 | 超管强制登出用户 | [超管] Token | code=0 | ⭐⭐⭐ |
| USER-074 | 强制登出后该用户所有 Token 吊销 | 强制登出前获取 Token，之后调用 API | Token 返回 40102 | ⭐⭐⭐ |
| USER-075 | 部门管理员强制登出本部门用户 | [部门管理员] Token | code=0 | ⭐⭐⭐ |
| USER-076 | 部门管理员强制登出其他部门用户 | [部门管理员] Token，user_id=其他部门 | code=40301 | ⭐⭐⭐ |

---

## 文档管理

### 4.1 上传文档（POST /api/docs/upload）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DOC-001 | 上传有效的 Markdown 文件 | [管理员] Token，.md 文件 ≤ 200MB，visibility="global" | code=0, status="processing", id/file_uuid/file_name/created_at | ⭐⭐⭐ |
| DOC-002 | 上传有效的 PDF 文件 | .pdf 文件 ≤ 200MB | code=0, status="processing" | ⭐⭐⭐ |
| DOC-003 | 上传有效的 DOCX 文件 | .docx 文件 ≤ 200MB | code=0, status="processing" | ⭐⭐⭐ |
| DOC-004 | 上传超过 200MB 的文件 | 文件大小 > 200MB | code=42202, "文件超过大小限制" | ⭐⭐⭐ |
| DOC-005 | 上传不支持的格式 | .txt / .exe / .jpg 等 | code=42201, "文件格式不支持" | ⭐⭐⭐ |
| DOC-006 | 员工尝试上传文档 | [员工] Token | code=40301 | ⭐⭐⭐ |
| DOC-007 | 无 Token 上传文档 | 不提供 Authorization 头 | code=40101 | ⭐⭐⭐ |
| DOC-008 | 上传时设置权限级别 | visibility="dept_only" / "non_customer" / "specific_users" | code=0 | ⭐⭐⭐ |
| DOC-009 | 上传时设置分类和版本号 | category="行政制度", version="v2.1" | code=0，元数据已保存 | ⭐⭐⭐ |
| DOC-010 | 部门管理员上传文档 | [部门管理员] Token | code=0，上传到本部门 | ⭐⭐⭐ |
| DOC-011 | 上传后文件系统验证 | 上传 .pdf，检查 /data/uploads/docs/{dept_id}/ | 文件应存在于正确的目录 | ⭐⭐ |
| DOC-012 | 重复上传相同文件 | 上传两次相同内容的文件 | 两次都返回 code=0，生成不同的 file_uuid | ⭐⭐⭐ |

### 4.2 文档列表（GET /api/docs）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DOC-013 | 超管查看所有文档 | [超管] Token，无过滤 | code=0, 返回所有文档（分页） | ⭐⭐⭐ |
| DOC-014 | 部门管理员查看本部门文档 | [部门管理员] Token，不传 dept_id | 返回本部门文档 | ⭐⭐⭐ |
| DOC-015 | 部门管理员查看其他部门文档 | [部门管理员] Token，dept_id=其他部门 | 应自动限制为本部门还是返回 40301？（需确认） | ⭐⭐⭐ |
| DOC-016 | 员工查看文档列表 | [员工] Token | 应仅返回有权限的文档（权限过滤） | ⭐⭐⭐ |
| DOC-017 | 按部门过滤 | dept_id=2 | 仅返回该部门的文档 | ⭐⭐⭐ |
| DOC-018 | 按状态过滤 | status="ready" | 仅返回已处理完成的文档 | ⭐⭐⭐ |
| DOC-019 | 按分类过滤 | category="行政制度" | 返回该分类的文档 | ⭐⭐⭐ |
| DOC-020 | 按关键词搜索 | keyword="出差" | 返回文件名包含"出差"的文档 | ⭐⭐⭐ |
| DOC-021 | 分页查询 | page=1, page_size=20 | 返回分页数据，total 正确 | ⭐⭐⭐ |
| DOC-022 | 文档权限过滤 | 查询权限为 "specific_users" 的文档 | 无权限用户不应在列表中看到该文档 | ⭐⭐⭐ |
| DOC-023 | 归档文档过滤 | 查看列表 | 归档文档（status="archived"）应默认不显示还是可选过滤？（需确认） | ⭐⭐ |

### 4.3 文档处理状态（GET /api/docs/{doc_id}/status）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DOC-024 | 查看处理中文档状态 | 刚上传的文档 | status="processing", chunk_count=null | ⭐⭐⭐ |
| DOC-025 | 查看已完成文档状态 | 处理完成的文档 | status="ready", chunk_count > 0, processing_ms > 0 | ⭐⭐⭐ |
| DOC-026 | 查看处理失败文档 | 处理失败的文档 | status="failed", error_message 包含失败原因 | ⭐⭐⭐ |
| DOC-027 | 轮询处理状态 | 定时调用此接口 | 每次调用返回最新状态 | ⭐⭐⭐ |
| DOC-028 | 查看不存在的文档 | doc_id=9999 | code=40401 | ⭐⭐⭐ |
| DOC-029 | 权限检查 | 查看无权限的文档 | code=40401（隐藏存在性）或 code=40301（需确认） | ⭐⭐⭐ |

### 4.4 修改文档元信息（PUT /api/docs/{doc_id}）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DOC-030 | 修改文档分类 | [管理员] Token，category="新分类" | code=0 | ⭐⭐⭐ |
| DOC-031 | 修改文档版本号 | version="v3.0" | code=0 | ⭐⭐⭐ |
| DOC-032 | 修改文档权限级别 | visibility="non_customer" | code=0 | ⭐⭐⭐ |
| DOC-033 | 部门管理员修改本部门文档 | [部门管理员] Token | code=0 | ⭐⭐⭐ |
| DOC-034 | 部门管理员修改其他部门文档 | [部门管理员] Token，doc_id=其他部门文档 | code=40301 | ⭐⭐⭐ |
| DOC-035 | 员工修改文档 | [员工] Token | code=40301 | ⭐⭐⭐ |
| DOC-036 | 修改不存在的文档 | doc_id=9999 | code=40401 | ⭐⭐⭐ |
| DOC-037 | 修改后验证数据更新 | 修改后查询详情 | 返回的 category/version/visibility 应为新值 | ⭐⭐⭐ |

### 4.5 设置文档权限（PUT /api/docs/{doc_id}/permissions）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DOC-038 | 为 specific_users 设置白名单 | [管理员] Token，visibility="specific_users"，user_ids=[3,7,12] | code=0 | ⭐⭐⭐ |
| DOC-039 | 全量覆盖权限列表 | 先设置 [3,7,12]，再设置 [3,5]，最后只有 [3,5] | 后续调用应仅返回 [3,5] | ⭐⭐⭐ |
| DOC-040 | 为非 specific_users 的文档设置权限 | visibility="global"，尝试设置 user_ids | code=400 或忽略该字段（需确认） | ⭐⭐ |
| DOC-041 | 跨部门权限验证 | 为其他部门文档设置权限 | 部门管理员应无权限（code=40301） | ⭐⭐⭐ |
| DOC-042 | 指定不存在的用户 | user_ids 包含不存在的用户 ID | code=40401 | ⭐⭐⭐ |
| DOC-043 | 指定其他部门的用户 | 为本部门文档指定其他部门用户 | code=40302, "跨部门操作被拒绝" | ⭐⭐⭐ |

### 4.6 查看文档权限（GET /api/docs/{doc_id}/permissions）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DOC-044 | 查看 specific_users 文档权限 | [管理员] Token，doc_id 为 specific_users 类型 | code=0, user_ids=[...], users 列表包含 id/username/display_name | ⭐⭐⭐ |
| DOC-045 | 查看其他类型文档权限 | visibility="global"，查看权限 | code=0 返回空列表还是提示？（需确认） | ⭐⭐ |
| DOC-046 | 跨部门查看权限 | 部门管理员查看其他部门文档的权限 | code=40301 | ⭐⭐⭐ |
| DOC-047 | 权限列表数据一致性 | 设置权限后立即查看 | 返回的用户列表应与设置的一致 | ⭐⭐⭐ |

### 4.7 归档文档（POST /api/docs/{doc_id}/archive）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DOC-048 | 归档文档 | [管理员] Token | code=0, data=null | ⭐⭐⭐ |
| DOC-049 | 归档后文档不参与检索 | 归档后调用对话接口查询 | 该文档不应在检索结果中 | ⭐⭐⭐ |
| DOC-050 | 归档后数据保留 | 归档后数据库仍存储该文档 | 超管查询应能看到（status="archived"） | ⭐⭐⭐ |
| DOC-051 | 部门管理员归档本部门文档 | [部门管理员] Token | code=0 | ⭐⭐⭐ |
| DOC-052 | 部门管理员归档其他部门文档 | [部门管理员] Token，doc_id=其他部门 | code=40301 | ⭐⭐⭐ |
| DOC-053 | 重复归档 | 已归档文档再归档 | code=0 或 code=400（待确认） | ⭐⭐ |

### 4.8 删除文档（DELETE /api/docs/{doc_id}）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| DOC-054 | 删除文档 | [超管] Token | code=0, data=null | ⭐⭐⭐ |
| DOC-055 | 删除后文件物理删除 | 删除后检查 /data/uploads/docs/ | 文件应不存在 | ⭐⭐ |
| DOC-056 | 删除后数据库清理 | 检查 documents/doc_chunks/embeddings 表 | 关联数据应全部删除 | ⭐⭐⭐ |
| DOC-057 | 删除后写入审计日志 | 检查 audit_logs 表 | 应有 action="doc.delete" 的记录 | ⭐⭐⭐ |
| DOC-058 | 部门管理员删除文档 | [部门管理员] Token，doc_id=本部门 | 应返回 40301（仅超管可删除）还是允许？（需确认） | ⭐⭐⭐ |
| DOC-059 | 删除不存在的文档 | doc_id=9999 | code=40401 | ⭐⭐⭐ |
| DOC-060 | 删除后无法再查询 | 删除后调用查询接口 | code=40401 | ⭐⭐⭐ |

---

## 对话聊天

### 5.1 发起流式对话（POST /api/chat/stream）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| CHAT-001 | 创建新会话 | [登录用户] Token，message="报销住宿上限是多少?", 不传 conversation_id | SSE 流，第一个事件：type="conversation_id", content=新分配的 ID | ⭐⭐⭐ |
| CHAT-002 | 在现有会话中继续对话 | 传入有效的 conversation_id | SSE 流，conversation_id 事件返回相同 ID | ⭐⭐⭐ |
| CHAT-003 | SSE 流式输出 token | 监听流中的 "token" 类型事件 | 应逐个推送 token，而不是一次性输出 | ⭐⭐⭐ |
| CHAT-004 | SSE 返回 sources | 问题涉及有关文档的内容 | 流中应包含 type="sources" 事件，包含 doc_id/chunk_id/doc_name/heading/page_no | ⭐⭐⭐ |
| CHAT-005 | SSE 流结束 | 完整的对话周期 | 最后应有 type="done", content="" 事件 | ⭐⭐⭐ |
| CHAT-006 | SSE 错误处理 | 模型服务故障 | 返回 type="error", content="错误信息" | ⭐⭐⭐ |
| CHAT-007 | 权限过滤检索 | 员工 A 提问，仅应返回 A 有权限的文档内容 | sources 中的文档应被权限过滤 | ⭐⭐⭐ |
| CHAT-008 | 员工查询对话 | [员工] Token | code=0，应正常流式输出 | ⭐⭐⭐ |
| CHAT-009 | 无 Token 对话 | 不提供 Authorization 头 | code=40101 | ⭐⭐⭐ |
| CHAT-010 | 信息脱敏处理 | 提问包含用户名/手机号 | LangGraph 脱敏节点应处理，外部 LLM 调用前已脱敏 | ⭐⭐⭐ |
| CHAT-011 | 空消息 | message="" | code=422 或 code=400 | ⭐⭐ |
| CHAT-012 | 过长消息 | message 超过合理长度限制 | code=422 或 code=400（需确认限制） | ⭐⭐ |
| CHAT-013 | 非 SSE 请求此接口 | 不设 Accept: text/event-stream | 应返回 SSE 还是错误？（需确认） | ⭐⭐ |
| CHAT-014 | 连接断开恢复 | SSE 连接中途断开 | 客户端应重新请求，服务端应生成新会话还是继续？（需确认） | ⭐⭐ |
| CHAT-015 | LangGraph 工作流完整性 | 监控整个流程 | 应经过：脱敏 → 意图识别 → 检索 → 生成 → 输出 | ⭐⭐⭐ |

### 5.2 会话列表（GET /api/chat/conversations）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| CHAT-016 | 获取当前用户会话列表 | [登录用户] Token | code=0, 返回该用户的所有 active 会话（分页），按 updated_at 倒序 | ⭐⭐⭐ |
| CHAT-017 | 会话分页 | page=1, page_size=10 | 返回第1页数据，total 准确 | ⭐⭐⭐ |
| CHAT-018 | 搜索会话标题 | keyword="报销" | 返回 title 包含"报销"的会话 | ⭐⭐⭐ |
| CHAT-019 | 不显示非 active 会话 | 已删除的会话 | 列表中不应显示 status≠"active" 的会话 | ⭐⭐⭐ |
| CHAT-020 | 每个用户仅看自己的会话 | 用户 A 的 Token 查询 | 不应看到用户 B 的会话 | ⭐⭐⭐ |
| CHAT-021 | 会话包含消息计数 | 返回数据 | 每个会话应包含 message_count | ⭐⭐⭐ |
| CHAT-022 | 无 Token 查询会话列表 | 不提供 Authorization 头 | code=40101 | ⭐⭐⭐ |

### 5.3 会话消息记录（GET /api/chat/conversations/{conversation_id}）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| CHAT-023 | 获取会话的完整消息 | [登录用户] Token，conversation_id=自己的会话 | code=0, 返回会话 title 和 messages 数组（user/assistant 交替） | ⭐⭐⭐ |
| CHAT-024 | 消息包含 sources | assistant 类型消息 | 应包含 sources 数组，每个 source 包含 doc_id/doc_name/heading/page_no | ⭐⭐⭐ |
| CHAT-025 | 消息排序 | 查看消息顺序 | 应按 created_at 升序（时间线顺序） | ⭐⭐⭐ |
| CHAT-026 | 用户消息 sources 为 null | user 类型的消息 | sources 应为 null | ⭐⭐⭐ |
| CHAT-027 | 权限验证 - 自己的会话 | 用户查看自己的会话 | code=0，可以查看 | ⭐⭐⭐ |
| CHAT-028 | 权限验证 - 其他用户会话 | [普通员工] 查看其他员工的会话 | code=40401（不透露存在性） | ⭐⭐⭐ |
| CHAT-029 | 部门管理员查看下属员工会话 | [部门管理员] Token，conversation_id=本部门员工会话 | code=0，可以查看（需确认是否可传 user_id 参数） | ⭐⭐⭐ |
| CHAT-030 | 查看不存在的会话 | conversation_id=9999 | code=40401 | ⭐⭐⭐ |
| CHAT-031 | 无 Token 查询 | 不提供 Authorization 头 | code=40101 | ⭐⭐⭐ |

### 5.4 重命名会话（PATCH /api/chat/conversations/{conversation_id}）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| CHAT-032 | 用户重命名自己的会话 | [登录用户] Token，title="出差报销相关" | code=0 | ⭐⭐⭐ |
| CHAT-033 | 重命名后验证数据更新 | 重命名后调用查询接口 | title 应为新值 | ⭐⭐⭐ |
| CHAT-034 | 尝试重命名他人会话 | [用户 A] 尝试重命名 [用户 B] 的会话 | code=40401 | ⭐⭐⭐ |
| CHAT-035 | 部门管理员重命名下属员工会话 | [部门管理员] Token | code=0 还是 code=40301？（需确认） | ⭐⭐ |
| CHAT-036 | 标题为空 | title="" | code=422 或接受空字符串（需确认） | ⭐⭐ |
| CHAT-037 | 重命名不存在的会话 | conversation_id=9999 | code=40401 | ⭐⭐⭐ |

### 5.5 删除会话（DELETE /api/chat/conversations/{conversation_id}）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| CHAT-038 | 用户删除自己的会话 | [登录用户] Token | code=0 | ⭐⭐⭐ |
| CHAT-039 | 删除后会话不可见 | 删除后调用会话列表 | 删除的会话不应出现 | ⭐⭐⭐ |
| CHAT-040 | 删除数据保留 | 删除会话后检查数据库 | 数据应逻辑删除（status 标记）还是物理删除？（需确认） | ⭐⭐ |
| CHAT-041 | 尝试删除他人会话 | [用户 A] 删除 [用户 B] 的会话 | code=40401 | ⭐⭐⭐ |
| CHAT-042 | 部门管理员删除下属员工会话 | [部门管理员] Token | code=0 还是 code=40301？（需确认） | ⭐⭐ |
| CHAT-043 | 超管删除任意用户会话 | [超管] Token | code=0 | ⭐⭐⭐ |
| CHAT-044 | 重复删除 | 删除后再删除 | code=40401 | ⭐⭐⭐ |

---

## 审计日志

### 6.1 审计日志列表（GET /api/admin/audit/logs）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| AUDIT-001 | 超管查看所有审计日志 | [超管] Token | code=0, 返回所有日志（分页）| ⭐⭐⭐ |
| AUDIT-002 | 部门管理员查看审计日志 | [部门管理员] Token | code=40301，仅超管可查看（待确认） | ⭐⭐⭐ |
| AUDIT-003 | 按 action 过滤 | action="user.create" | 仅返回创建用户的日志 | ⭐⭐⭐ |
| AUDIT-004 | 按操作人过滤 | operator_id=5 | 仅返回该用户操作的日志 | ⭐⭐⭐ |
| AUDIT-005 | 按资源类型过滤 | resource_type="user" | 仅返回与用户相关的日志 | ⭐⭐⭐ |
| AUDIT-006 | 按日期范围过滤 | start_date="2026-05-01", end_date="2026-06-01" | 返回指定范围内的日志 | ⭐⭐⭐ |
| AUDIT-007 | 按结果过滤 | result="fail" | 仅返回失败的操作 | ⭐⭐⭐ |
| AUDIT-008 | 分页查询 | page=1, page_size=20 | 返回分页数据 | ⭐⭐⭐ |
| AUDIT-009 | 日志包含完整信息 | 查询结果 | 应包含 operator_name/action/resource_type/resource_id/new_value/ip_address/result/created_at | ⭐⭐⭐ |
| AUDIT-010 | IP 地址记录 | 从不同 IP 执行操作 | 日志应记录正确的 IP 地址 | ⭐⭐⭐ |

---

## 系统配置

### 7.1 获取系统配置（GET /api/admin/system/config）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| CONFIG-001 | 超管获取配置 | [超管] Token | code=0, 返回所有配置键值对 | ⭐⭐⭐ |
| CONFIG-002 | 部门管理员获取配置 | [部门管理员] Token | code=40301 | ⭐⭐⭐ |
| CONFIG-003 | 验证默认配置值 | 查询结果 | max_sessions_per_user=200, max_messages_per_session=500 等 | ⭐⭐⭐ |
| CONFIG-004 | 模型配置 | 查询结果 | embed_model="nomic-embed-text", chat_model_employee="qwen2.5:7b" 等 | ⭐⭐⭐ |

### 7.2 更新配置（PUT /api/admin/system/config/{key}）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| CONFIG-005 | 超管更新配置 | [超管] Token，key="max_sessions_per_user", value=300 | code=0 | ⭐⭐⭐ |
| CONFIG-006 | 更新后验证数据 | 更新后调用查询接口 | 值应为新设置 | ⭐⭐⭐ |
| CONFIG-007 | 更新不存在的 key | key="invalid_key" | code=40401 | ⭐⭐⭐ |
| CONFIG-008 | 值类型验证 | key="max_sessions_per_user", value="abc"（应为整数） | code=422 | ⭐⭐ |
| CONFIG-009 | 部门管理员更新配置 | [部门管理员] Token | code=40301 | ⭐⭐⭐ |

---

## LangGraph 工作流

### 8.1 脱敏节点（Sanitize Node）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| WORKFLOW-001 | 脱敏姓名 | 消息包含真实姓名"张三" | 内部状态应脱敏为"[姓名]"，流向外部 LLM 时已脱敏 | ⭐⭐⭐ |
| WORKFLOW-002 | 脱敏手机号 | 消息包含手机号"13800138000" | 脱敏为"[手机号]" | ⭐⭐⭐ |
| WORKFLOW-003 | 脱敏身份证号 | 消息包含身份证号 | 脱敏为"[身份证号]" | ⭐⭐⭐ |
| WORKFLOW-004 | 脱敏邮箱 | 消息包含公司邮箱 | 脱敏为"[邮箱]" | ⭐⭐⭐ |
| WORKFLOW-005 | 脱敏编号 | 消息包含员工编号"RD001" | 脱敏为"[员工编号]" | ⭐⭐⭐ |
| WORKFLOW-006 | 多项同时脱敏 | 消息同时包含姓名、手机号、邮箱 | 应全部脱敏 | ⭐⭐⭐ |
| WORKFLOW-007 | 本地 Ollama 不脱敏 | 仅调用本地 Ollama | 内部状态保留原文，脱敏应仅在调用外部 API 前进行 | ⭐⭐⭐ |

### 8.2 意图识别节点（Intent Node）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| WORKFLOW-008 | 识别知识库查询意图 | "报销住宿上限是多少?" | intent="knowledge_query", confidence > 0.8 | ⭐⭐⭐ |
| WORKFLOW-009 | 识别闲聊意图 | "你好啊" | intent="chitchat" 或 "greeting" | ⭐⭐⭐ |
| WORKFLOW-010 | 识别反馈意图 | "这个答案不对" | intent="feedback" 或 "correction" | ⭐⭐⭐ |
| WORKFLOW-011 | 意图识别置信度 | 边界问题 | 置信度较低时应标记为 low_confidence | ⭐⭐ |

### 8.3 检索节点（Retrieval Node）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| WORKFLOW-012 | 权限过滤检索 | 员工 A 查询，文档 D 设为 specific_users（不含 A） | 检索结果不应包含 D | ⭐⭐⭐ |
| WORKFLOW-013 | 部门权限检索 | 员工 A（HR 部门）查询，文档为 "non_customer" | 应包含该文档（非客服可见） | ⭐⭐⭐ |
| WORKFLOW-014 | 向量相似度排序 | 查询与多个文档匹配 | 应返回相似度最高的前 N 个 chunk | ⭐⭐⭐ |
| WORKFLOW-015 | 检索不到文档 | 查询与库内任何文档都不相关 | 应返回空结果或低置信度标记 | ⭐⭐⭐ |
| WORKFLOW-016 | 同一 Embedding 模型 | 检索准确率 | 文档向量化和查询向量化使用同一模型，保证空间一致性 | ⭐⭐⭐ |

### 8.4 生成节点（Generation Node）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| WORKFLOW-017 | 基于检索结果生成 | 检索到 3 个相关 chunk | 回答应基于这些 chunk 的内容 | ⭐⭐⭐ |
| WORKFLOW-018 | 无检索结果时生成 | 检索为空 | 应返回"无法在文档中找到相关信息"或类似提示 | ⭐⭐⭐ |
| WORKFLOW-019 | 引用信息准确性 | 生成的回答引用具体 chunk | 引用的页码、段落应准确对应 | ⭐⭐⭐ |
| WORKFLOW-020 | 模型选择 | 员工查询 → 使用 qwen2.5:7b，管理员查询 → 使用 deepseek-chat | 应根据用户角色选择不同模型 | ⭐⭐⭐ |

### 8.5 SSE 输出节点（SSE Output Node）

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| WORKFLOW-021 | token 逐个推送 | 生成 100 个 token 的回答 | 应通过 SSE 逐个推送，而不是批量 | ⭐⭐⭐ |
| WORKFLOW-022 | sources 事件 | 生成结束前 | 应推送 type="sources" 事件，包含引用的文档列表 | ⭐⭐⭐ |
| WORKFLOW-023 | done 事件 | 完整生成 | 最后应推送 type="done" 事件标记结束 | ⭐⭐⭐ |
| WORKFLOW-024 | error 事件 | 中途发生错误 | 应推送 type="error" 事件，连接关闭 | ⭐⭐⭐ |

---

## 跨模块集成

### 9.1 完整登录-对话流程

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| INTEGRATION-001 | 从登录到对话的完整流程 | 1. 登录 2. 上传文档 3. 对话提问 | 应能端到端完成，会话和消息正确保存 | ⭐⭐⭐ |
| INTEGRATION-002 | 权限链路完整性 | 部门管理员上传文档，员工查询 | 应能正确过滤权限，员工仅看到有权限的内容 | ⭐⭐⭐ |
| INTEGRATION-003 | 审计日志链路 | 执行创建用户、上传文档、对话等操作 | 所有操作应正确记录在 audit_logs | ⭐⭐⭐ |

### 9.2 并发场景

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| INTEGRATION-004 | 多用户并发对话 | 5 个用户同时调用 /api/chat/stream | 应能并发处理，不互相干扰 | ⭐⭐⭐ |
| INTEGRATION-005 | 同时上传多个文档 | 3 个用户同时上传文档 | 应能正确入队处理，不丢失 | ⭐⭐⭐ |
| INTEGRATION-006 | Token 过期并发刷新 | 多个请求同时刷新 Token | 应生成唯一新 Token，旧 Token 一致性 | ⭐⭐ |

### 9.3 数据一致性

| ID | 测试场景 | 输入 | 预期输出 | 优先级 |
|---|---|---|---|---|
| INTEGRATION-007 | 用户删除后的数据清理 | 删除用户，检查关联数据 | 用户的会话、消息应如何处理？（逻辑删除还是级联删除？需确认） | ⭐⭐ |
| INTEGRATION-008 | 文档权限变更一致性 | 修改文档权限后立即对话 | 应应用最新的权限规则 | ⭐⭐⭐ |
| INTEGRATION-009 | 会话消息计数一致性 | 添加消息后查询列表 | message_count 应递增 | ⭐⭐⭐ |

---

## 附录：测试用例统计

| 模块 | 总用例数 | 优先级⭐⭐⭐ | 优先级⭐⭐ | 优先级⭐ |
|---|---|---|---|---|
| 认证（Auth） | 18 | 15 | 3 | 0 |
| 部门管理 | 12 | 10 | 2 | 0 |
| 用户管理 | 32 | 26 | 6 | 0 |
| 文档管理 | 28 | 22 | 6 | 0 |
| 对话聊天 | 18 | 16 | 2 | 0 |
| 审计日志 | 4 | 4 | 0 | 0 |
| 系统配置 | 6 | 4 | 2 | 0 |
| LangGraph 工作流 | 12 | 11 | 1 | 0 |
| 跨模块集成 | 9 | 7 | 2 | 0 |
| **总计** | **139** | **115** | **24** | **0** |

---

## 备注

1. 部分测试用例标记为"需确认"，表示依赖于产品或架构的最终设计决策
2. 所有权限相关测试应覆盖三级角色系统的完整验证
3. 所有数据修改操作应验证审计日志的完整记录
4. SSE 流式输出相关测试应验证信息推送的实时性和完整性
5. 数据库一致性测试应关注脏数据、孤立数据等场景
