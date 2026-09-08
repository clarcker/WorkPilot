"""
认证模块路由。

POST /api/auth/login              登录
POST /api/auth/logout             登出（吊销 Token）
POST /api/auth/refresh            刷新 Token
POST /api/auth/change-password    修改密码
GET  /api/auth/me                 获取当前用户信息
PATCH /api/auth/me                修改昵称
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import AuditAction, write_audit
from core.config import settings
from core.deps import get_current_user
from core.logger import logger
from core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from db.models import RevokedToken, User
from db.session import async_session_factory, get_db
from schemas.auth import (
    ChangePasswordRequest,
    LoginData,
    LoginRequest,
    MeData,
    UpdateMeRequest,
    UserBrief,
)
from schemas.common import BaseResp

router = APIRouter()


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _get_ip(request: Request) -> str | None:
    """优先读 X-Forwarded-For（Nginx 代理场景），否则取直连 IP"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _build_login_data(user: User, db: AsyncSession) -> LoginData:
    """签发 Token 并组装登录响应体（成功路径复用）"""
    token, jti, expires_at = create_access_token(user.id, user.role.value)

    # 计算 expires_in（秒）
    now = datetime.now(timezone.utc)
    expires_in = max(0, int((expires_at - now).total_seconds()))

    # 查询部门信息（不能访问 lazy 关系，需显式查询）
    dept_name = None
    dept_code = None
    if user.dept_id:
        from db.models import Department
        dept = await db.get(Department, user.dept_id)
        if dept:
            dept_name = dept.dept_name
            dept_code = dept.dept_code

    return LoginData(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        must_change_password=user.must_change_password,
        user=UserBrief(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            real_name=user.real_name,
            role=user.role.value,
            dept_id=user.dept_id,
            dept_name=dept_name,
            dept_code=dept_code,
        ),
    )


# ------------------------------------------------------------------
# POST /login
# ------------------------------------------------------------------
@router.post("/login", response_model=BaseResp[LoginData])
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = _get_ip(request)

    # 查找用户
    user: User | None = await db.scalar(
        select(User).where(User.username == req.username)
    )

    # ---- 失败分支：用独立 session 提交，不影响主 session ----
    async def _record_failure(reason: str, error_code: int) -> None:
        async with async_session_factory() as audit_db:
            if user:
                # 累计失败次数
                user_in_audit = await audit_db.get(User, user.id)
                if user_in_audit:
                    user_in_audit.failed_login_count += 1
                    # 达到阈值则锁定
                    if user_in_audit.failed_login_count >= settings.login_max_fail_count:
                        user_in_audit.locked_at = datetime.now(timezone.utc)
            await write_audit(
                audit_db,
                operator_id=user.id if user else None,
                operator_name=user.real_name if user else req.username,
                action=AuditAction.AUTH_LOGIN,
                ip_address=ip,
                result="fail",
                detail=reason,
            )
            await audit_db.commit()

    # 用户不存在
    if not user:
        await _record_failure("用户不存在", 40001)
        logger.warning("Login fail: user not found | username={username}", username=req.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40001, "message": "账号或密码错误"},
        )

    # 账号禁用
    if not user.is_active:
        logger.warning("Login fail: account disabled | username={username}", username=req.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40003, "message": "账号已禁用，请联系管理员"},
        )

    # 账号锁定
    if user.locked_at:
        logger.warning("Login fail: account locked | username={username}", username=req.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40002, "message": "账号已锁定，请联系管理员解锁"},
        )

    # 密码错误
    if not verify_password(req.password, user.password_hash):
        await _record_failure("密码错误", 40001)
        logger.warning("Login fail: wrong password | username={username}", username=user.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40001, "message": "账号或密码错误"},
        )

    # ---- 成功分支 ----
    # 重置失败计数，记录登录时间
    user.failed_login_count = 0
    user.last_login_at = datetime.now(timezone.utc)

    login_data = await _build_login_data(user, db)

    logger.info("User login success | user={username}", username=user.username)

    await write_audit(
        db,
        operator_id=user.id,
        operator_name=user.real_name,
        action=AuditAction.AUTH_LOGIN,
        ip_address=ip,
        result="success",
    )

    return BaseResp.ok(login_data)


# ------------------------------------------------------------------
# POST /logout
# ------------------------------------------------------------------
@router.post("/logout", response_model=BaseResp[None])
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 从 Header 取出 token 解析 jti + expires_at
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
        jti: str = payload["jti"]
        exp: int = payload["exp"]
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    except (JWTError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40101, "message": "Token 无效"},
        )

    # 加入黑名单
    db.add(RevokedToken(jti=jti, expires_at=expires_at))

    logger.info("User logout | user={username}", username=current_user.username)

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.AUTH_LOGOUT,
        ip_address=_get_ip(request),
    )

    return BaseResp.ok()


# ------------------------------------------------------------------
# POST /refresh
# ------------------------------------------------------------------
@router.post("/refresh", response_model=BaseResp[LoginData])
async def refresh_token(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 吊销旧 Token
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
        old_jti: str = payload["jti"]
        old_exp: int = payload["exp"]
        old_expires_at = datetime.fromtimestamp(old_exp, tz=timezone.utc)
    except (JWTError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40101, "message": "Token 无效"},
        )

    db.add(RevokedToken(jti=old_jti, expires_at=old_expires_at))

    # 签发新 Token
    login_data = await _build_login_data(current_user, db)
    return BaseResp.ok(login_data)


# ------------------------------------------------------------------
# POST /change-password
# （使用 get_current_user 而非 get_active_user，允许 must_change_password=True 的用户访问）
# ------------------------------------------------------------------
@router.post("/change-password", response_model=BaseResp[None])
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 若不是首次改密（must_change_password=False），需验证旧密码
    if not current_user.must_change_password:
        if not req.old_password:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": 42200, "message": "请提供当前密码"},
            )
        if not verify_password(req.old_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": 40001, "message": "当前密码错误"},
            )

    # 新密码不能与旧密码相同
    if req.new_password and verify_password(req.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 42200, "message": "新密码不能与当前密码相同"},
        )

    # 更新密码
    current_user.password_hash = hash_password(req.new_password)
    current_user.must_change_password = False

    # 吊销当前 Token（改密后强制重新登录）
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
        jti: str = payload["jti"]
        exp: int = payload["exp"]
        db.add(RevokedToken(jti=jti, expires_at=datetime.fromtimestamp(exp, tz=timezone.utc)))
    except (JWTError, KeyError):
        pass  # Token 解析失败不阻断改密流程

    logger.info("Password changed | user={username}", username=current_user.username)

    await write_audit(
        db,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        action=AuditAction.AUTH_CHANGE_PWD,
        ip_address=_get_ip(request),
    )

    return BaseResp.ok(message="密码修改成功，请重新登录")


# ------------------------------------------------------------------
# GET /me
# ------------------------------------------------------------------
@router.get("/me", response_model=BaseResp[MeData])
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 查部门信息
    dept_name = None
    dept_code = None
    if current_user.dept_id:
        from db.models import Department
        dept = await db.get(Department, current_user.dept_id)
        if dept:
            dept_name = dept.dept_name
            dept_code = dept.dept_code

    return BaseResp.ok(
        MeData(
            id=current_user.id,
            username=current_user.username,
            employee_no=current_user.employee_no,
            display_name=current_user.display_name,
            real_name=current_user.real_name,
            role=current_user.role.value,
            dept_id=current_user.dept_id,
            dept_name=dept_name,
            dept_code=dept_code,
            email=current_user.email,
            must_change_password=current_user.must_change_password,
            last_login_at=current_user.last_login_at,
        )
    )


# ------------------------------------------------------------------
# PATCH /me  （修改昵称）
# ------------------------------------------------------------------
@router.patch("/me", response_model=BaseResp[None])
async def update_me(
    req: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.display_name = req.display_name
    return BaseResp.ok(message="昵称修改成功")
