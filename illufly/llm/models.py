from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, List, Union

from enum import Enum
import uuid
import time

from ..rocksdb import IndexedRocksDB

class Thread(BaseModel):
    """连续对话跟踪"""
    @classmethod
    def register_indexes(cls, db: IndexedRocksDB):
        db.register_model(cls.__name__, cls)
        db.register_index(cls.__name__, cls, "created_at")

    @classmethod
    def get_prefix(cls, user_id: str):
        return f"thread-{user_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str):
        return f"{cls.get_prefix(user_id)}-{thread_id}"

    user_id: Union[str, None] = Field(default=None, description="用户ID")
    thread_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="对话ID")
    title: str = Field(default="", description="连续对话标题")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="对话创建时间")

class ToolCalling(BaseModel):
    tool_id: str = Field(default="", description="工具ID")
    name: str = Field(default="", description="工具名称")
    arguments: str = Field(default="", description="工具参数")

class ChunkType(Enum):
    AI_DELTA = "ai_delta"
    AI_MESSAGE = "ai_message"
    USER_INPUT = "user_input"

class DialougeChunk(BaseModel):
    user_id: Union[str, None] = Field(default=None, description="用户ID")
    thread_id: Union[str, None] = Field(default=None, description="线程ID")
    dialouge_id: str = Field(
        default_factory=lambda: f"{int(time.time()*1000):013d}-{time.monotonic_ns()%1000:03d}",
        description="对话ID，格式：时间戳(毫秒)-单调递增值"
    )
    created_at: float = Field(
        default_factory=lambda: datetime.now().timestamp(),
        description="创建时间"
    )
    chunk_type: ChunkType = Field(default=ChunkType.USER_INPUT, description="角色")
    input_messages: List[Dict[str, Any]] = Field(default=[], description="输入消息")
    output_text: str = Field(default="", description="输出消息")
    tool_calls: List[ToolCalling] = Field(default=[], description="工具调用")

    @classmethod
    def register_indexes(cls, db: IndexedRocksDB):
        db.register_model(cls.__name__, cls)
        db.register_index(cls.__name__, cls, "created_at")

    @classmethod
    def get_prefix(cls, user_id: str, thread_id: str):
        return f"dlg-{user_id}-{thread_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str, dialouge_id: str):
        return f"{cls.get_prefix(user_id, thread_id)}-{dialouge_id}"

    def model_dump(self):
        common_fields = {
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "dialouge_id": self.dialouge_id,
            "created_at": self.created_at,
        }
        if self.chunk_type == ChunkType.USER_INPUT:
            return {
                **common_fields,
                "chunk_type": self.chunk_type,
                "input_messages": self.input_messages,
            }
        elif self.chunk_type == ChunkType.AI_DELTA:
            return {
                **common_fields,
                "chunk_type": self.chunk_type,
                "output_text": self.output_text,
            }
        elif self.chunk_type == ChunkType.AI_MESSAGE:
            return {
                **common_fields,
                "chunk_type": self.chunk_type,
                "output_text": self.output_text,
                "tool_calls": [v.model_dump() for v in self.tool_calls],
            }
        else:
            raise ValueError(f"Invalid chunk type: {self.chunk_type}")

