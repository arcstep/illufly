from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from enum import Enum
from pydantic import BaseModel, Field, model_validator, ConfigDict
import time
import json
import logging
import uuid
from datetime import datetime

from .enum import BlockType, ReplyState, RequestStep

logger = logging.getLogger(__name__)

class BaseBlock(BaseModel):
    """基础数据块"""
    request_id: str = Field(default="")
    created_at: float = Field(default_factory=lambda: time.time())

    model_config = ConfigDict(use_enum_values=True)

class ReplyBlock(BaseBlock):
    """响应块"""
    state: ReplyState = Field(default=ReplyState.SUCCESS)
    result: Any = None

class ReplyAcceptedBlock(ReplyBlock):
    """响应块"""
    state: ReplyState = ReplyState.ACCEPTED
    subscribe_address: Union[str, None]

class ReplyReadyBlock(ReplyBlock):
    """响应块"""
    state: ReplyState = ReplyState.READY

class ReplyProcessingBlock(ReplyBlock):
    """响应块"""
    state: ReplyState = ReplyState.PROCESSING

class ReplyErrorBlock(ReplyBlock):
    """响应块"""
    state: ReplyState = ReplyState.ERROR
    error: str

class RequestBlock(BaseBlock):
    """请求块"""
    request_step: RequestStep
    func_name: str = "default"
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}

class StreamingBlock(BaseBlock):
    """流式数据块基类"""
    block_type: BlockType

    @property
    def content(self) -> Any:
        """获取内容"""
        raise NotImplementedError
    
    @property
    def is_error(self) -> bool:
        """是否是错误块"""
        return self.block_type == BlockType.ERROR

    @classmethod
    def create_block(cls, block_type: BlockType, **kwargs):
        """创建一个数据块"""
        if block_type == BlockType.TEXT_CHUNK:
            return TextChunk(**kwargs)
        elif block_type == BlockType.TEXT_FINAL:
            return TextFinal(**kwargs)
        elif block_type == BlockType.TOOL_CALL_CHUNK:
            return ToolCallChunk(**kwargs)
        elif block_type == BlockType.TOOL_CALL_FINAL:
            return ToolCallFinal(**kwargs)
        elif block_type == BlockType.USAGE:
            return UsageBlock(**kwargs)
        elif block_type == BlockType.PROGRESS:
            return ProgressBlock(**kwargs)
        elif block_type == BlockType.START:
            return StartBlock(**kwargs)
        elif block_type == BlockType.END:
            return EndBlock(**kwargs)
        elif block_type == BlockType.ERROR:
            return ErrorBlock(**kwargs)

        return cls(block_type=block_type, **kwargs)

class PesistentMessageBlock(StreamingBlock):
    """持久化消息块"""
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="请求ID")
    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="消息ID")
    message_type: str = Field(default="text", description="消息类型", pattern="^(text|image)$")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="消息开始构造时间")
    completed_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="消息完成时间")
    role: str = Field(default="user", description="消息角色", pattern="^(user|assistant|system|tool)$")
    text: str = Field(default="", description="消息内容")
    images: List[str] = Field(default=[], description="图片列表")
    tool_calls: List[Dict[str, Any]] = Field(default=[], description="工具调用列表")
    tool_id: str = Field(default="", description="工具ID")

    @property
    def content(self) -> Dict[str, Any]:
        # 工具调用结果
        resp = {}
        if self.tool_calls:
            resp = {
                "role": self.role,
                "tool_calls": self.tool_calls,
                "content": self.text
            }
        # 文本消息
        elif self.message_type == "text":
            resp = {
                "role": self.role,
                "content": self.text
            }
        # 图片消息
        elif self.message_type == "image":
            text = {
                "type": "text",
                "text": self.text
            } if self.text else {}
            images = [
                {
                    "type": "image",
                    "image_url": image
                }
                for image in self.images
            ]
            resp = {
                "role": self.role,
                "content": [*text, *images]
            }

        # 工具调用消息，补充 tool_id
        if self.role == "tool" and self.tool_id:
            resp.update({
                "tool_id": self.tool_id,
            })
        
        return resp

class QueryBlock(PesistentMessageBlock):
    """查询块"""
    block_type: BlockType = BlockType.QUERY

class AnswerBlock(PesistentMessageBlock):
    """回答块"""
    block_type: BlockType = BlockType.ANSWER

class TextChunk(StreamingBlock):
    """文本块"""
    block_type: BlockType = BlockType.TEXT_CHUNK
    model: Optional[str] = None
    text: str

    @property
    def content(self) -> str:
        return self.text

class TextFinal(StreamingBlock):
    """文本结束块"""
    block_type: BlockType = BlockType.TEXT_FINAL
    model: Optional[str] = None
    text: str

    @property
    def content(self) -> str:
        return self.text

class ToolCallChunk(StreamingBlock):
    """工具调用块"""
    block_type: BlockType = BlockType.TOOL_CALL_CHUNK
    model: Optional[str] = None
    tool_call_id: Optional[str] = None  # 工具调用ID
    tool_name: Optional[str] = None  # 工具名称
    arguments: str = ""  # 工具参数（逐步累积）

    @property
    def content(self) -> Dict[str, Any]:
        logger.info(f"ToolCallChunk: {self.tool_call_id} {self.tool_name} {self.arguments}")
        return {
            "type": "function",
            "id": self.tool_call_id,
            "function": {
                "name": self.tool_name,
                "arguments": self.arguments
            }
        }

class ToolCallFinal(StreamingBlock):
    """工具调用结束块"""
    block_type: BlockType = BlockType.TOOL_CALL_FINAL
    model: Optional[str] = None
    tool_call_id: str  # 工具调用ID
    tool_name: str  # 工具名称
    arguments: str  # 完整的工具参数

    @property
    def content(self) -> dict:
        return {
            "type": "function",
            "id": self.tool_call_id,
            "function": {
                "name": self.tool_name,
                "arguments": self.arguments
            }
        }

class UsageBlock(StreamingBlock):
    """使用情况块"""
    block_type: BlockType = BlockType.USAGE
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    prompt_cache_hit_tokens: Optional[int] = None
    prompt_cache_miss_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    model: Optional[str] = None
    provider: Optional[str] = None

    @property
    def content(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "prompt_cache_hit_tokens": self.prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": self.prompt_cache_miss_tokens,
            "completion_tokens_details": {
                "reasoning_tokens": self.reasoning_tokens,
            }
        }

class ProgressBlock(StreamingBlock):
    """进度块"""
    block_type: BlockType = BlockType.PROGRESS
    step: int
    total_steps: int
    percentage: float
    message: str

    @property
    def content(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "total_steps": self.total_steps,
            "percentage": self.percentage,
            "message": self.message
        }

class StartBlock(StreamingBlock):
    """开始块"""
    block_type: BlockType = BlockType.START

    @property
    def content(self) -> None:
        return None

class EndBlock(StreamingBlock):
    """结束块"""
    block_type: BlockType = BlockType.END

    @property
    def content(self) -> None:
        return None

class ErrorBlock(StreamingBlock):
    """错误块"""
    block_type: BlockType = BlockType.ERROR
    error: str

    @property
    def content(self) -> str:
        return self.error

# 消息类型注册表
MESSAGE_TYPES = {
    'TextChunk': TextChunk,
    'StreamingBlock': StreamingBlock,
    'EndBlock': EndBlock,
    'ReplyBlock': ReplyBlock,
    'ErrorBlock': ErrorBlock,
    'RequestBlock': RequestBlock,
    'QueryBlock': QueryBlock,
    'AnswerBlock': AnswerBlock,
}
