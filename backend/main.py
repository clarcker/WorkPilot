"""
WorkPilot v2 — FastAPI 入口

启动：
    # Windows / 开发
    uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
    uv run fastapi dev main.py
    # 多 worker 验收（Windows 也可用）；gunicorn 仅 Linux/Docker（fcntl）
    uv run uvicorn main:app --workers 4 --port 8000
    # Linux / Docker 生产
    uv run gunicorn -k uvicorn.workers.UvicornWorker -w 4 main:app -b 0.0.0.0:8000
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.logger import setup_logger, logger

from api import auth as auth_router
from api import departments as dept_router
from api import chat as chat_router
from api import documents as doc_router
from api import users as user_router
from api import audit as audit_router
from api import system as system_router
from api import eval as eval_router
from api import reimbursements as reimb_router
from api import traces as traces_router
from api import tickets as tickets_router
from api import ticket_admin as ticket_admin_router
from api import quality as quality_router
from api import notifications as notif_router
from api import embeddings_admin as emb_router


# ------------------------------------------------------------------
# 生命周期：启动 / 关闭钩子
# ------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    setup_logger(
        log_dir=settings.log_dir,
        log_level=settings.log_level,
        log_rotation=settings.log_rotation,
        log_retention=settings.log_retention,
        log_console=settings.log_console,
        environment=settings.environment,
    )
    logger.info("WorkPilot v2 starting | env={env}", env=settings.environment)
    for w in settings.validate_for_startup():
        logger.warning("[security] {w}", w=w)
    # 模型分档路由一览（排查「改了配置仍走本地」先看这行）
    from core.config import describe_llm_routing
    logger.info("[llm] routing | {r}", r=describe_llm_routing())

    # P4 prompt 版本：启动即校验，缺失直接失败
    try:
        from services.prompt_loader import current_prompt_set, load_prompts
        load_prompts()
        logger.info("[prompts] set_version={v}", v=current_prompt_set())
    except Exception as exc:
        logger.error("[prompts] 加载失败（阻断启动）: {e}", e=exc)
        raise

    # P2 APScheduler（PostgreSQLJobStore）
    from services.scheduler import start_scheduler, stop_scheduler
    await start_scheduler()

    # 保留 cleanup_loop 作为 scheduler 失败时的兜底（单 worker 有效）
    from services.cleanup import cleanup_loop
    stop_event = asyncio.Event()
    cleanup_task = asyncio.create_task(cleanup_loop(stop_event))

    yield

    # 关闭
    stop_scheduler()
    stop_event.set()
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("WorkPilot v2 shutting down")


# ------------------------------------------------------------------
# 应用实例
# ------------------------------------------------------------------
app = FastAPI(
    title="WorkPilot v2",
    description="企业智能 Agent 系统",
    version="0.1.0",
    lifespan=lifespan,
    # 生产环境建议关闭文档
    # docs_url=None,
    # redoc_url=None,
)

# ------------------------------------------------------------------
# 跨域：开发默认 localhost:5173；生产通过 CORS_ORIGINS 配置白名单
# ------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求日志中间件
from core.logger import RequestLoggingMiddleware
app.add_middleware(RequestLoggingMiddleware)

# 限流：登录 + 对话流（内存滑动窗口，单机用）
from core.ratelimit import RateLimitMiddleware
app.add_middleware(
    RateLimitMiddleware,
    login_per_minute=settings.rate_limit_login_per_minute,
    chat_per_5min=settings.rate_limit_chat_per_5min,
)


# ------------------------------------------------------------------
# 全局异常处理：统一格式化为 BaseResp 风格
# ------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(
        "HTTP exception | {method} {path} | status={status} | detail={detail}",
        method=request.method,
        path=request.url.path,
        status=exc.status_code,
        detail=exc.detail,
    )
    # HTTPException.detail 若已是 dict（含 code + message），直接用
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        body = {"code": exc.detail["code"], "data": None, "message": exc.detail["message"]}
    else:
        body = {"code": exc.status_code, "data": None, "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception | {method} {path} | error={error}",
        method=request.method,
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"code": 50001, "data": None, "message": "服务器内部错误"},
    )


# ------------------------------------------------------------------
# 路由注册
# ------------------------------------------------------------------
app.include_router(auth_router.router,   prefix="/api/auth",              tags=["认证"])
app.include_router(dept_router.router,   prefix="/api/admin/departments",  tags=["部门管理"])
app.include_router(user_router.router,   prefix="/api/admin/users",        tags=["用户管理"])
app.include_router(doc_router.router,    prefix="/api/docs",               tags=["文档管理"])
app.include_router(chat_router.router,   prefix="/api/chat",               tags=["对话聊天"])
app.include_router(audit_router.router,  prefix="/api/admin/audit",        tags=["审计日志"])
app.include_router(system_router.router, prefix="/api/admin/system",       tags=["系统配置"])
app.include_router(eval_router.router,   prefix="/api/eval",               tags=["评测"])
app.include_router(reimb_router.router,  prefix="/api/reimbursements",     tags=["报销申请"])
app.include_router(traces_router.router, prefix="/api/admin/traces",       tags=["Agent Trace"])
app.include_router(tickets_router.router, prefix="/api/tickets",           tags=["IT 工单"])
app.include_router(ticket_admin_router.router, prefix="/api/admin/tickets", tags=["工单处理"])
app.include_router(quality_router.router,   prefix="/api/quality",         tags=["评测/反馈/缺口"])
app.include_router(notif_router.router,     prefix="/api/admin",            tags=["通知"])
app.include_router(emb_router.router,       prefix="/api/admin",            tags=["embedding"])


# ------------------------------------------------------------------
# 健康检查（Docker / 负载均衡探针用）
# ------------------------------------------------------------------
@app.get("/health", tags=["运维"])
async def health():
    return {"status": "ok"}
