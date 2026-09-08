"""
安全工具：JWT 签发/验证、bcrypt、随机密码生成。
"""
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from core.config import settings

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_token",
    "generate_random_password",
]


# ------------------------------------------------------------------
# 密码
# ------------------------------------------------------------------

def hash_password(password: str) -> str:
    """返回 bcrypt hash 字符串"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def generate_random_password(length: int = 12) -> str:
    """
    生成满足复杂度要求的随机密码：
    至少 1 个大写 + 1 个小写 + 1 个数字 + 1 个特殊字符。
    """
    special = "!@#$%"
    alphabet = string.ascii_letters + string.digits + special
    while True:
        pwd = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice(special),
        ] + [secrets.choice(alphabet) for _ in range(length - 4)]
        secrets.SystemRandom().shuffle(pwd)
        result = "".join(pwd)
        # 二次校验（理论上必定满足，保险起见）
        if (any(c.isupper() for c in result)
                and any(c.islower() for c in result)
                and any(c.isdigit() for c in result)
                and any(c in special for c in result)):
            return result


# ------------------------------------------------------------------
# JWT
# ------------------------------------------------------------------

def create_access_token(
    user_id: int,
    role: str,
) -> tuple[str, str, datetime]:
    """
    签发 JWT。
    返回 (token_str, jti, expires_at)。
    jti 用于存入 revoked_tokens 实现主动吊销。
    """
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)

    payload = {
        "sub":  str(user_id),
        "jti":  jti,
        "role": role,
        "iat":  now,
        "exp":  expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def decode_token(token: str) -> dict:
    """
    解码并验证 JWT。
    失败时抛出 jose.JWTError（调用方处理）。
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
