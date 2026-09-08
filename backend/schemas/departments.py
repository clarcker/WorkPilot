"""
部门管理 Schema。
"""
from datetime import datetime

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# 请求
# ------------------------------------------------------------------

class DeptCreate(BaseModel):
    dept_code: str = Field(
        ...,
        min_length=1,
        max_length=20,
        pattern=r'^[A-Z0-9]+$',
        description="部门代码，大写字母或数字，如 HR、RD001",
    )
    dept_name: str = Field(..., min_length=1, max_length=100, description="部门名称")


class DeptUpdate(BaseModel):
    dept_name: str = Field(..., min_length=1, max_length=100)


# ------------------------------------------------------------------
# 响应
# ------------------------------------------------------------------

class DeptOut(BaseModel):
    id: int
    dept_code: str
    dept_name: str
    user_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}
