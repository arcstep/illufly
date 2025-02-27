from typing import Any, TypeVar, Generic, Optional, List
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum

import logging
logger = logging.getLogger(__name__)

T = TypeVar('T')

class HttpMethod(str, Enum):
    GET = "get"
    POST = "post"
    PUT = "put"
    DELETE = "delete"

class Result(BaseModel, Generic[T]):
    """返回结果"""

    @classmethod
    def ok(cls, data: Optional[T] = None, message: str = "操作成功") -> "Result[T]":
        return cls(success=True, message=message, data=data)

    @classmethod
    def fail(cls, error: str, message: str = "操作失败") -> "Result[T]":
        logger.warning(f"操作失败: {error}")
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

class ChatMessage(BaseModel):
    role: str
    content: str
    tool_calls: Optional[List[dict]] = Field(default=None, description="工具调用")

class OpenaiRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="消息列表")
    model: str = Field(default=None, description="模型名称")
    frequency_penalty: Optional[float] = Field(default=None, description="频率惩罚")
    max_tokens: Optional[int] = Field(default=None, description="最大token数")
    presence_penalty: Optional[float] = Field(default=None, description="存在惩罚")
    response_format: Optional[dict] = Field(default=None, description="响应格式")
    stream: Optional[bool] = Field(default=False, description="是否流式")
    stream_options: Optional[dict] = Field(default=None, description="流式选项")
    temperature: Optional[float] = Field(default=None, description="温度")
    top_p: Optional[float] = Field(default=None, description="top_p")
    tools: Optional[List[dict]] = Field(default=None, description="工具列表")
    tool_choice: Optional[dict] = Field(default=None, description="工具选择")
    logprobs: Optional[bool] = Field(default=None, description="是否返回logprobs")
    top_logprobs: Optional[int] = Field(default=None, description="返回的top logprobs数量")
    modalities: Optional[List[str]] = Field(default=None, description="模态")
    audio: Optional[dict] = Field(default=None, description="音频")
    seed: Optional[int] = Field(default=None, description="随机种子")
    stop: Optional[List[str]] = Field(default=None, description="停止词")
    n: Optional[int] = Field(default=None, ge=1, le=10, description="返回的候选数量")
    logit_bias: Optional[dict] = Field(default=None, description="logit偏置")
    enable_search: Optional[bool] = Field(default=None, description="是否启用搜索")
    user: Optional[str] = Field(default=None, description="用户标识")
    # 预留未考虑到的参数
    extra: Optional[dict] = Field(default=None, description="用于兼容未支持的参数")

    def model_dump(self, *args, **kwargs):
        kwargs.setdefault('exclude_none', True)
        result = super().model_dump(*args, **kwargs)
        
        # 移除空列表、空字典和空字符串
        return {
            k: v for k, v in result.items() 
            if not (v is None or 
                    (isinstance(v, (list, dict, str)) and len(v) == 0) or
                    (isinstance(v, (float, int)) and v == 0 and k not in ['temperature', 'frequency_penalty', 'presence_penalty', 'top_p']))
        }

