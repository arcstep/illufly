from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from enum import Enum
from pydantic import BaseModel, Field, model_validator, ConfigDict
import time
import json
import logging
import uuid
from datetime import datetime

from .utils import serialize
from .enum import BlockType, ReplyState, RequestStep

logger = logging.getLogger(__name__)

class ZmqServiceState(Enum):
    """ZMQ 服务状态枚举"""
    INIT = 0       # 初始化状态
    RUNNING = 1    # 正常运行
    RECONNECTING = 2 # 重连中
    STOPPING = 3   # 停止中
    STOPPED = 4    # 已停止


@serialize
class BaseBlock(BaseModel):
    """基础数据块"""
    request_id: str = Field(default="")
    response_id: str = Field(default="")
    service_name: str = Field(default="")
    created_at: float = Field(default_factory=lambda: time.time())
    completed_at: float = Field(default_factory=lambda: time.time())

    model_config = ConfigDict(use_enum_values=True)

@serialize
class ReplyBlock(BaseBlock):
    """响应块"""
    state: ReplyState = Field(default=ReplyState.SUCCESS)
    result: Any = None

@serialize
class ReplyAcceptedBlock(ReplyBlock):
    """响应块"""
    state: ReplyState = ReplyState.ACCEPTED
    subscribe_address: Union[str, None]

@serialize
class ReplyReadyBlock(ReplyBlock):
    """响应块"""
    state: ReplyState = ReplyState.READY

@serialize
class ReplyProcessingBlock(ReplyBlock):
    """响应块"""
    state: ReplyState = ReplyState.PROCESSING

@serialize
class ReplyErrorBlock(ReplyBlock):
    """响应块"""
    state: ReplyState = ReplyState.ERROR
    error: str

@serialize
class RequestBlock(BaseBlock):
    """请求块"""
    request_step: RequestStep
    func_name: str = "default"
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}

@serialize
class StreamingBlock(BaseBlock):
    """流式数据块基类"""
    block_type: BlockType
    role: str = ""
    message_type: str = ""
    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
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

@serialize
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

@serialize
class StartBlock(StreamingBlock):
    """开始块"""
    block_type: BlockType = BlockType.START

    @property
    def content(self) -> None:
        return None

@serialize
class EndBlock(StreamingBlock):
    """结束块"""
    block_type: BlockType = BlockType.END

    @property
    def content(self) -> None:
        return None

@serialize
class ErrorBlock(StreamingBlock):
    """错误块"""
    block_type: BlockType = BlockType.ERROR
    error: str

    @property
    def content(self) -> str:
        return self.error

