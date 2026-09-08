"""
FastAPI 依赖注入：用户认证、角色校验。

使用方式：
    @router.get("/foo")
    async def foo(user: User = Depends(get_current_user)):
        ...

    @router.post("/admin/bar")
    async def bar(user: User = Depends(require_admin)):
        ...
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RevokedToken, User, UserRole
from db.session import get_db
from core.security import decode_token

# FastAPI 内置 Bearer 提取器
_bearer = HTTPBearer(auto_error=True)


# ------------------------------------------------------------------
# 基础认证依赖：只验证 Token + 用户是否存在/激活
# （不检查 must_change_password，改密接口需要用这个）
# ------------------------------------------------------------------
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials

    # 1. 解码 JWT
    try:
        payload = decode_token(token)
        user_id: int = int(payload["sub"])
        jti: str = payload["jti"]
        iat: datetime = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40101, "message": "Token 无效或已过期"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. 检查 Token 是否已被主动吊销（jti 黑名单）
    revoked = await db.scalar(
        select(RevokedToken).where(RevokedToken.jti == jti)
    )
    if revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40102, "message": "Token 已吊销，请重新登录"},
        )

    # 3. 查询用户
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40101, "message": "用户不存在"},
        )

    # 4. 检查账号状态
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40003, "message": "账号已禁用，请联系管理员"},
        )

    # 5. 检查是否被强制登出（tokens_invalidated_before）
    if user.tokens_invalidated_before and iat <= user.tokens_invalidated_before:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": 40102, "message": "已被管理员强制登出，请重新登录"},
        )

    return user


# ------------------------------------------------------------------
# 完整用户依赖：额外检查 must_change_password
# 大多数业务接口使用此依赖；改密、登出、获取自身信息使用 get_current_user
# ------------------------------------------------------------------
async def get_active_user(
    user: User = Depends(get_current_user),
) -> User:
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": 40103, "message": "请先修改初始密码后再使用系统"},
        )
    return user


# ------------------------------------------------------------------
# 角色校验工厂函数
# ------------------------------------------------------------------
def require_roles(*roles: UserRole):
    """
    用法：
        @router.post("/admin/x")
        async def x(user = Depends(require_roles(UserRole.super_admin))):
    """
    async def _dep(user: User = Depends(get_active_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 40301, "message": "无权限执行此操作"},
            )
        return user
    return _dep


# 常用组合（直接作为 Depends 参数传入）
require_admin       = require_roles(UserRole.dept_admin, UserRole.super_admin)
require_super_admin = require_roles(UserRole.super_admin)
