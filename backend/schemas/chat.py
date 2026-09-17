"""
聊天模块 Schema。
"""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------
# 请求
# ------------------------------------------------------------------

class ChatRequest(BaseModel):
    query:           str      = Field(..., min_length=1, max_length=4000, description="用户问题")
    conversation_id: int | None = Field(default=None, description="None = 新建会话")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("查询内容不能为空")
        return v


# ------------------------------------------------------------------
# 会话 & 消息响应
# ------------------------------------------------------------------

class ConversationOut(BaseModel):
    id:            int
    title:         str | None
    status:        str
    message_count: int
    created_at:    datetime
    updated_at:    datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id:              int
    role:            str   # user | assistant
    content:         str
    sources:         list[dict] | None
    created_at:      datetime

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages:     list[MessageOut]


class ConversationRename(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="新标题")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("标题不能为空")
        return v
