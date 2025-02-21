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
    text: str = ""

    @property
    def content(self) -> Any:
        """获取内容"""
        return self.text
    
    @property
    def is_error(self) -> bool:
        """是否是错误块"""
        return self.block_type == BlockType.ERROR

    @classmethod
    def create_block(cls, block_type: BlockType, **kwargs):
        """创建一个数据块"""
        if block_type == BlockType.PROGRESS:
            return ProgressBlock(**kwargs)
        elif block_type == BlockType.START:
            return StartBlock(**kwargs)
        elif block_type == BlockType.END:
            return EndBlock(**kwargs)
        elif block_type == BlockType.ERROR:
            return ErrorBlock(**kwargs)

        return cls(block_type=block_type, **kwargs)

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
    'StreamingBlock': StreamingBlock,
    'EndBlock': EndBlock,
    'ReplyBlock': ReplyBlock,
    'ErrorBlock': ErrorBlock,
    'RequestBlock': RequestBlock,
}
