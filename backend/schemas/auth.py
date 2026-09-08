"""
认证模块的请求/响应 Schema。
"""
import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------
# 请求
# ------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def strip_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("用户名不能为空")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("密码不能为空")
        return v


class ChangePasswordRequest(BaseModel):
    old_password: str = Field("", max_length=128)   # 首次改密可为空
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码长度至少8位")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码必须包含大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码必须包含小写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码必须包含数字")
        return v


class UpdateMeRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("昵称不能为空")
        # 防止 XSS
        if re.search(r'[<>"\'&]', v):
            raise ValueError("昵称包含非法字符")
        return v


# ------------------------------------------------------------------
# 响应
# ------------------------------------------------------------------

class UserBrief(BaseModel):
    """登录/me 接口中的用户摘要"""
    id: int
    username: str
    display_name: str
    real_name: str
    role: str
    dept_id: int | None
    dept_name: str | None
    dept_code: str | None

    model_config = {"from_attributes": True}


class LoginData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int            # 秒
    must_change_password: bool
    user: UserBrief


class MeData(BaseModel):
    id: int
    username: str
    employee_no: str
    display_name: str
    real_name: str
    role: str
    dept_id: int | None
    dept_name: str | None
    dept_code: str | None
    email: str | None
    must_change_password: bool
    last_login_at: datetime | None

    model_config = {"from_attributes": True}
