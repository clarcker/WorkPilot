"""
文档管理 Schema。
"""
from datetime import datetime

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# 响应
# ------------------------------------------------------------------

class DocOut(BaseModel):
    id:                int
    file_uuid:         str
    file_name:         str
    file_size:         int         # bytes
    file_type:         str         # pdf / docx / md
    dept_id:           int
    dept_name:         str | None = None
    visibility:        str         # global / non_customer / dept_only / specific_users
    status:            str         # processing / ready / failed / archived
    lifecycle:         str = "effective"   # effective / superseded / draft
    effective_date:    str | None = None
    supersedes_doc_id: int | None = None
    supersedes_name:   str | None = None
    superseded_by_name: str | None = None
    error_message:     str | None
    category:          str | None
    version:           str | None
    uploaded_by:       int
    uploaded_by_name:  str | None = None
    created_at:        datetime
    updated_at:        datetime
    chunk_count:       int | None = None   # 分块数量，仅详情接口填充

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# 请求
# ------------------------------------------------------------------

class DocUpdate(BaseModel):
    """可更新字段：不含文件内容，修改后不触发重新向量化。"""
    visibility: str | None = Field(
        default=None,
        description="global | non_customer | dept_only | specific_users",
    )
    category:   str | None = Field(default=None, max_length=100)
    version:    str | None = Field(default=None, max_length=50)
    lifecycle:  str | None = Field(
        default=None,
        description="effective | superseded | draft",
    )
    effective_date: str | None = Field(default=None, description="YYYY-MM-DD")


class VersionChainItem(BaseModel):
    id: int
    file_name: str
    lifecycle: str
    effective_date: str | None = None
    status: str
    is_self: bool = False


class DocPermissionSet(BaseModel):
    """PUT /docs/{id}/permissions 请求体：替换整个指定人员白名单。"""
    user_ids: list[int] = Field(
        default=[],
        description="有权访问的用户 ID 列表（visibility=specific_users 时有效）",
    )


# ------------------------------------------------------------------
# 权限白名单成员
# ------------------------------------------------------------------

class PermissionMember(BaseModel):
    user_id:      int
    username:     str
    real_name:    str
    employee_no:  str
    granted_at:   datetime

    model_config = {"from_attributes": True}
