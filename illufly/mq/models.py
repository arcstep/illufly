from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from enum import Enum
from pydantic import BaseModel, Field, model_validator, ConfigDict
import time
import json

class BlockType(str, Enum):
    START = "start"
    CHUNK = "chunk"
    TOOLS_CALL = "tools_call"
    USAGE = "usage"
    PROGRESS = "progress"
    IMAGE = "image"
    VISION = "vision"
    ERROR = "error"
    END = "end"
    CONTENT = "content"

class ToolCallFunction(BaseModel):
    name: str
    arguments: str

class ToolCall(BaseModel):
    id: str
    type: str = "function"
    function: ToolCallFunction

class Usage(BaseModel):
    request_id: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    model: Optional[str] = None
    provider: Optional[str] = None

class ImageContent(BaseModel):
    url: Optional[str] = None
    base64: Optional[str] = None
    detail: str = "auto"
    type: str = "image"

class MessageContent(BaseModel):
    type: str
    text: Optional[str] = None
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    detail: Optional[str] = None

class ProgressContent(BaseModel):
    """进度信息模型"""
    step: int  # 当前步骤
    total_steps: int  # 总步骤数
    percentage: float  # 进度百分比
    message: str  # 进度消息

class StreamingBlock(BaseModel):
    """流式数据块"""
    block_type: BlockType
    block_content: Optional[Union[Dict[str, Any], str, None]] = None  # 允许字典、字符串或 None
    content: Optional[Any] = None
    topic: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)

    def model_dump(self) -> Dict[str, Any]:
        """保持原有的序列化行为"""
        data = super().model_dump()
        # 确保 block_content 字段存在
        if self.block_content is None:
            data["block_content"] = ""
        return data

    @classmethod
    def create_tools_call(cls, tool_data: Dict[str, Any], topic: str = "") -> "StreamingBlock":
        """创建工具调用块"""
        tool_call = ToolCall(**tool_data)
        return cls(
            block_type=BlockType.TOOLS_CALL,
            topic=topic,
            block_content=tool_call.model_dump_json()
        )

    @classmethod
    def create_usage(cls, usage_data: Dict[str, Any], topic: str = "") -> "StreamingBlock":
        """创建使用情况块"""
        usage = Usage(**usage_data)
        return cls(
            block_type=BlockType.USAGE,
            topic=topic,
            block_content=usage.model_dump_json()
        )

    @classmethod
    def create_chunk(cls, content: str, topic: str = "") -> "StreamingBlock":
        """创建文本块"""
        return cls(
            block_type=BlockType.CHUNK,
            content=content,
            topic=topic
        )

    @classmethod
    def create_start(cls, topic: str = "") -> "StreamingBlock":
        """创建开始块"""
        return cls(block_type=BlockType.START, topic=topic)

    @classmethod
    def create_end(cls, topic: str = "") -> "StreamingBlock":
        """创建结束块"""
        return cls(block_type=BlockType.END, topic=topic)

    @classmethod
    def create_error(cls, error: str, topic: str = "") -> "StreamingBlock":
        """创建错误块"""
        return cls(block_type=BlockType.ERROR, content=error, topic=topic)

    @classmethod
    def create_vision_input(cls, messages: List[Dict[str, Any]], topic: str = "") -> "StreamingBlock":
        """创建视觉输入块"""
        content_list = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                for content in msg["content"]:
                    if content.get("type") == "image":
                        content_list.append(ImageContent(
                            url=content.get("image_url"),
                            base64=content.get("image_base64"),
                            detail=content.get("detail", "auto")
                        ))
        return cls(
            block_type=BlockType.VISION,
            topic=topic,
            block_content=MessageContent(
                type="image",
                images=content_list
            ).model_dump_json()
        )

    @classmethod
    def create_progress(cls, percentage: float, message: str, step: int, total_steps: int, topic: str = None, seq: int = None) -> "StreamingBlock":
        """创建进度块"""
        progress = ProgressContent(
            total_steps=total_steps,
            step=step,
            percentage=percentage,
            message=message
        )
        return cls(
            block_type=BlockType.PROGRESS,
            block_content=progress.model_dump(),
            topic=topic,
        )

    def get_tools_call(self) -> Optional[ToolCall]:
        """获取工具调用数据"""
        if self.block_type == BlockType.TOOLS_CALL and self.block_content:
            return ToolCall.model_validate_json(self.block_content)
        return None

    def get_usage(self) -> Optional[Usage]:
        """获取使用情况数据"""
        if self.block_type == BlockType.USAGE and self.block_content:
            return Usage.model_validate_json(self.block_content)
        return None

    def get_vision_content(self) -> Optional[List[ImageContent]]:
        """获取视觉内容"""
        if self.block_type == BlockType.VISION and self.block_content:
            content = MessageContent.model_validate_json(self.block_content)
            return content.images if hasattr(content, "images") else None
        return None

    def get_progress(self) -> Optional[ProgressContent]:
        """获取进度内容"""
        if self.block_type == BlockType.PROGRESS and self.block_content:
            return ProgressContent.model_validate(self.block_content)
        return None
