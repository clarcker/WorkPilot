"""
认证相关的测试辅助函数
"""

from datetime import datetime, timedelta, timezone
import uuid

from jose import jwt

from core.config import settings


def create_expired_token(user_id: int, role: str = "employee", hours: int = -1) -> str:
    """创建已过期的 Token"""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=hours)
    payload = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
        "role": role,
        "iat": now - timedelta(hours=abs(hours) + 1),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_custom_token(user_id: int, role: str = "employee", **extra_claims) -> str:
    """创建带自定义 claims 的 Token"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=8),
        **extra_claims,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
