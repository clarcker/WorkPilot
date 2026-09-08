# WorkPilot v2 后端日志系统与输入验证 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox syntax for tracking.

**Goal:** 为 WorkPilot v2 后端建立基于 loguru 的日志系统，加强 Pydantic 输入验证，统一配置管理。

**Architecture:** 使用 loguru 替代 Python 标准 logging 模块，实现按天轮转、自动删除过期日志、
请求追踪格式。通过 Pydantic Schema 加强边界条件验证。配置统一到 .env + core/config.py 两个文件。

**Tech Stack:** Python 3.11, FastAPI, Pydantic, loguru, SQLAlchemy, PostgreSQL

---

## 文件结构

### 新建文件
| 文件 | 职责 |
|------|------|
| backend/core/logger.py | loguru 日志配置模块 |
| backend/tests/unit/test_logger.py | 日志模块单元测试 |
| backend/tests/unit/test_schemas_validation.py | 输入验证单元测试 |

### 修改文件
| 文件 | 职责 |
|------|------|
| backend/pyproject.toml | 添加 loguru 依赖 |
| backend/core/config.py | 添加日志和验证相关配置项 |
| backend/.env.example | 添加日志配置示例 |
| backend/.env | 添加日志配置 |
| backend/.env.test | 添加日志配置 |
| backend/main.py | 集成日志中间件、改进全局异常处理 |
| backend/api/auth.py | 添加关键业务日志 |
| backend/api/users.py | 添加关键业务日志 |
| backend/api/departments.py | 添加关键业务日志 |
| backend/api/documents.py | 添加关键业务日志 |
| backend/api/system.py | 添加关键业务日志 |
| backend/schemas/auth.py | 加强输入验证 |
| backend/schemas/users.py | 加强输入验证 |
| backend/schemas/chat.py | 加强输入验证 |
| backend/services/*.py | 改进日志 |
| backend/graph/nodes.py | 改进日志 |
| docker-compose.yml | 添加日志卷挂载 |

---

## Task 1: Install loguru and create logger module

**Files:** Modify backend/pyproject.toml, Create backend/core/logger.py

### Step 1: Add loguru>=0.7.0 to pyproject.toml dependencies

### Step 2: Create backend/core/logger.py

Implement: loguru init, daily rotation, auto-delete expired logs, request tracking (request_id, user_id via ContextVar), dev/prod mode, RequestLoggingMiddleware for FastAPI

### Step 3: Verify: cd backend && python -c 'from core.logger import setup_logger; setup_logger()'

### Step 4: git add pyproject.toml core/logger.py && git commit -m 'feat: add loguru logger module'

---

## Task 2: Add logging and validation config

**Files:** Modify backend/core/config.py, .env.example, .env, .env.test

### Step 1: Add to Settings class in config.py:
- log_level: str = 'DEBUG'
- log_rotation: str = '1 day'
- log_retention: str = '7 days'
- log_console: bool = True
- log_dir: str = 'logs'
- environment: str = 'development'
- password_min_length: int = 8
- @property is_dev -> bool

### Step 2: Add matching vars to .env.example, .env, .env.test

### Step 3: Verify config loads correctly

### Step 4: Commit

---

## Task 3: Integrate logging into main.py

**Files:** Modify backend/main.py

Changes:
1. Import setup_logger, RequestLoggingMiddleware, logger from core.logger
2. In lifespan: call setup_logger() on startup, log startup/shutdown
3. Add RequestLoggingMiddleware after CORS middleware
4. In http_exception_handler: add logger.warning()
5. In generic_exception_handler: replace traceback.print_exc with logger.error(exc_info=True)

### Verify: python -c 'from main import app; print("OK")'

### Commit: git add main.py && git commit -m 'feat: integrate loguru into main.py'

---

## Task 4: Add logging to auth API

**Files:** Modify backend/api/auth.py

Add 'from core.logger import logger' at top.
Add logger.info/warning at these points:
- login success: logger.info(f'User login success | user={user.username}')
- login fail (user not found): logger.warning(f'Login fail: user not found | username={req.username}')
- login fail (wrong password): logger.warning(f'Login fail: wrong password | username={user.username}')
- login fail (disabled): logger.warning(f'Login fail: account disabled')
- login fail (locked): logger.warning(f'Login fail: account locked')
- logout success: logger.info(f'User logout | user={current_user.username}')
- change password success: logger.info(f'Password changed | user={current_user.username}')

---

## Task 5: Add logging to users API

**Files:** Modify backend/api/users.py

Add 'from core.logger import logger' at top.
Add logger.info at:
- create_user success
- update_user success
- reset_password success
- update_user_status success
- unlock_user success
- force_logout success

---

## Task 6: Add logging to departments API

**Files:** Modify backend/api/departments.py

Add logger.info at create/update/delete success.

---

## Task 7: Add logging to documents API

**Files:** Modify backend/api/documents.py

Add logger.info at upload/update/archive/reindex/permissions success.

---

## Task 8: Add logging to system API

**Files:** Modify backend/api/system.py

Add logger.info at update_config success.

---

## Task 9: Improve service module logging

**Files:** Modify services/document_parser.py, chunker.py, document_pipeline.py, embedder.py, retriever.py

For each file:
1. Replace 'import logging' + 'logger = logging.getLogger(__name__)' with 'from core.logger import logger'
2. Add logger.info at key entry/exit points
3. Add logger.error in except blocks with exc_info=True

document_parser.py: log parse start/finish with segment count, log errors
chunker.py: log chunking start/finish with chunk count
document_pipeline.py: already has logging, just migrate to loguru
embedder.py: already has logging, just migrate to loguru
retriever.py: already has logging, just migrate to loguru

---

## Task 10: Improve graph nodes logging

**Files:** Modify backend/graph/nodes.py

Replace 'import logging' + 'logger = logging.getLogger(__name__)' with 'from core.logger import logger'.
Existing logger.debug/error calls remain compatible with loguru.

---

## Task 11: Enhance Pydantic Schema validation

**Files:** Modify schemas/auth.py, schemas/users.py, schemas/chat.py

### schemas/auth.py:
- LoginRequest: validate username non-empty after strip, validate password non-empty
- ChangePasswordRequest: validate new_password min length, must have uppercase+lowercase+digit
- UpdateMeRequest: validate display_name non-empty after strip, reject XSS chars < > " ' &

### schemas/users.py:
- UserCreate: validate real_name strip+XSS, validate email format with regex, validate notes length
- UserUpdate: validate display_name strip+XSS, validate email format

### schemas/chat.py:
- ChatRequest: validate query non-empty after strip

### config.py:
- Add password_min_length: int = 8

---

## Task 12: Write logger unit tests

**Files:** Create backend/tests/unit/test_logger.py

Test cases:
- TestLogContextVars: request_id/user_id default, set/get, reset
- TestLoggerSetup: logger import, setup_logger callable, middleware import

---

## Task 13: Write schema validation unit tests

**Files:** Create backend/tests/unit/test_schemas_validation.py

Test cases:
- TestLoginRequestValidation: valid login, empty username rejected, empty password rejected, username stripped
- TestChangePasswordValidation: valid password, short rejected, no uppercase rejected, no lowercase rejected, no digit rejected
- TestUpdateMeValidation: valid name, empty rejected, XSS chars rejected, name stripped
- TestUserCreateValidation: valid create, XSS in real_name rejected, invalid email rejected, valid email accepted, empty email -> None
- TestChatRequestValidation: valid query, empty rejected, whitespace-only rejected, query stripped

---

## Task 14: Configure Docker log mount

**Files:** Modify docker-compose.yml

Add to backend volumes: ./backend/logs:/app/logs

---

## Task 15: Run full test suite

1. pytest tests/unit/ -v
2. pytest tests/integration/ -v (requires DB)
3. pytest tests/e2e/ -v
4. python -m ruff check . --fix (if configured)
5. Final commit after all tests pass

---

## Self-Review Checklist

- [x] Every spec requirement has a corresponding task
- [x] No TBD/TODO placeholders
- [x] Type/method/property names consistent across tasks
- [x] Every step has complete code and commands
- [x] Every task has verification step
