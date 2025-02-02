from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from enum import Enum
from pydantic import BaseModel, Field, model_validator, ConfigDict
import time
import json

from .enum import BlockType, ReplyState, RequestStep

class BaseBlock(BaseModel):
    """基础数据块"""
    request_id: str
    created_at: float = Field(default_factory=lambda: time.time())

    model_config = ConfigDict(use_enum_values=True)

class ReplyBlock(BaseBlock):
    """响应块"""
    state: ReplyState
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

class TextChunk(StreamingBlock):
    """文本块"""
    block_type: BlockType = BlockType.TEXT_CHUNK
    seq: int = 0
    text: str

    @property
    def content(self) -> str:
        return self.text

class TextFinal(StreamingBlock):
    """文本结束块"""
    block_type: BlockType = BlockType.TEXT_FINAL
    text: str
    chunks: List[TextChunk] = []

    @property
    def content(self) -> str:
        return self.text

class ToolCallChunk(StreamingBlock):
    """工具调用块"""
    block_type: BlockType = BlockType.TOOL_CALL_CHUNK
    seq: int = 0
    id: Optional[str] = None  # 工具调用ID
    name: Optional[str] = None  # 工具名称
    arguments: str = ""  # 工具参数（逐步累积）
    index: Optional[int] = None  # 工具调用的索引

    @property
    def content(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            "index": self.index
        }

class ToolCallFinal(StreamingBlock):
    """工具调用结束块"""
    block_type: BlockType = BlockType.TOOL_CALL_FINAL
    id: str  # 工具调用ID
    name: str  # 工具名称
    arguments: str  # 完整的工具参数
    index: int  # 工具调用的索引
    chunks: List[ToolCallChunk] = []  # 包含的所有chunk

    @property
    def content(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            "index": self.index
        }

class UsageBlock(StreamingBlock):
    """使用情况块"""
    block_type: BlockType = BlockType.USAGE
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    model: Optional[str] = None
    provider: Optional[str] = None

    @property
    def content(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "provider": self.provider
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
    'RequestBlock': RequestBlock
}
