"""
通用响应结构。

所有接口返回统一的 BaseResp[T] 包装：
    {"code": 0, "data": {...}, "message": "ok"}
    {"code": 40001, "data": null, "message": "账号或密码错误"}
"""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class BaseResp(BaseModel, Generic[T]):
    code: int = 0
    data: T | None = None
    message: str = "ok"

    @classmethod
    def ok(cls, data: T = None, message: str = "ok") -> "BaseResp[T]":
        return cls(code=0, data=data, message=message)

    @classmethod
    def fail(cls, code: int, message: str) -> "BaseResp[None]":
        return cls(code=code, data=None, message=message)


class PagedData(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
