from typing import Any, TypeVar, Generic, Optional
from pydantic import BaseModel, ConfigDict

T = TypeVar('T')

class Result(BaseModel, Generic[T]):
    """返回结果"""

    @classmethod
    def ok(cls, data: Optional[T] = None, message: str = "操作成功") -> "Result[T]":
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, error: str, message: str = "操作失败") -> "Result[T]":
        return cls(success=False, message=message, error=error)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,  # 允许任意类型
        from_attributes=True,  # 允许从对象属性读取（原 orm_mode）
    )
    
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
    data: Optional[T] = None

    def is_ok(self) -> bool:
        return self.success

    def is_fail(self) -> bool:
        return not self.success
    
    