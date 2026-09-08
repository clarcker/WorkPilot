"""
用户管理 Schema。
"""
import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------
# 请求
# ------------------------------------------------------------------

class UserCreate(BaseModel):
    real_name:   str      = Field(..., min_length=1, max_length=100, description="真实姓名")
    username:    str      = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r'^[a-z][a-z0-9]*$',
        description="用户名，小写字母开头，只含小写字母和数字，不可修改",
    )
    employee_no: str      = Field(..., min_length=2, max_length=20, description="员工编号，如 HR001")
    dept_id:     int | None = Field(default=None, description="所属部门 ID")
    role:        str      = Field(
        default="employee",
        description="角色：employee（普通员工）| dept_admin（部门管理员）",
    )
    email:       str | None = Field(default=None, max_length=255)
    notes:       str | None = Field(default=None, description="备注")

    @field_validator("real_name")
    @classmethod
    def validate_real_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("真实姓名不能为空")
        if re.search(r'[<>"\'&]', v):
            raise ValueError("姓名包含非法字符")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        # 简单邮箱格式校验
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("邮箱格式不正确")
        return v

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if len(v) > 500:
                raise ValueError("备注长度不能超过500字符")
        return v


class UserUpdate(BaseModel):
    """可更新字段。dept_admin 只能改 display_name / email / notes；super_admin 可改所有字段。"""
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    email:        str | None = Field(default=None, max_length=255)
    dept_id:      int | None = Field(default=None, description="仅 super_admin 可改")
    role:         str | None = Field(default=None, description="仅 super_admin 可改")
    notes:        str | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("昵称不能为空")
            if re.search(r'[<>"\'&]', v):
                raise ValueError("昵称包含非法字符")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("邮箱格式不正确")
        return v


class UserStatusUpdate(BaseModel):
    is_active: bool = Field(..., description="true=启用，false=禁用")


# ------------------------------------------------------------------
# 响应
# ------------------------------------------------------------------

class UserOut(BaseModel):
    id:                   int
    username:             str
    employee_no:          str
    display_name:         str
    real_name:            str
    role:                 str
    dept_id:              int | None
    dept_name:            str | None = None
    dept_code:            str | None = None
    email:                str | None
    is_active:            bool
    locked_at:            datetime | None
    failed_login_count:   int
    must_change_password: bool
    last_login_at:        datetime | None
    created_at:           datetime
    notes:                str | None

    model_config = {"from_attributes": True}


class UserCreateOut(UserOut):
    """创建用户时额外返回初始密码，供管理员告知用户。"""
    init_password: str


# ------------------------------------------------------------------
# 辅助响应
# ------------------------------------------------------------------

class SuggestUsernameOut(BaseModel):
    suggested:   str = Field(..., description="建议用户名（可能含序号后缀）")
    pinyin_base: str = Field(..., description="纯拼音基础（无后缀）")


class SuggestEmployeeNoOut(BaseModel):
    suggested: str = Field(..., description="建议员工编号，如 HR024")
    dept_code: str
    next_seq:  int  = Field(..., description="序号，如 24")


class ResetPasswordOut(BaseModel):
    new_password:         str
    must_change_password: bool = True
