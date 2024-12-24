from typing import Any, TypeVar, Generic, Optional
from dataclasses import dataclass

T = TypeVar('T')

@dataclass
class Result(Generic[T]):
    """返回结果"""
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
    data: Optional[T] = None

    @classmethod
    def ok(cls, data: Optional[T] = None, message: str = "操作成功") -> "Result[T]":
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, error: str, message: str = "操作失败") -> "Result[T]":
        return cls(success=False, message=message, error=error)
