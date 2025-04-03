from pydantic import BaseModel, Field, computed_field, model_validator
from datetime import datetime
from typing import Dict, Any, List, Union

from enum import Enum
import uuid
import time
import hashlib

from ..rocksdb import IndexedRocksDB

class MemoryQA(BaseModel):
    """
    使用主题、问题、答案这样的标准形式来表示用户反馈或用户经验。
    """
    user_id: Union[str, None] = Field(default=None, description="用户ID")
    topic: str = Field(default="", description="话题")
    question_hash: str = Field(default="", description="问题的hash值")
    question: str = Field(default="", description="问题")
    answer: str = Field(default="", description="答案")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="创建时间")

    def model_post_init(self, __context: Any) -> None:
        """Pydantic v2 初始化后处理方法"""
        super().model_post_init(__context)
        # 计算并设置问题哈希值
        self.question_hash = hashlib.sha256(self.question.encode("utf-8")).hexdigest()

    @classmethod
    def register_indexes(cls, db: IndexedRocksDB):
        db.register_model(cls.__name__, cls)
        db.register_index(cls.__name__, cls, "topic")
        db.register_index(cls.__name__, cls, "created_at")

    @classmethod
    def get_prefix(cls, user_id: str):
        return f"mem-{user_id}"

    @classmethod
    def get_key(cls, user_id: str, topic: str, question_hash: str):
        return f"{cls.get_prefix(user_id)}-{topic}-{question_hash}"

    def to_retrieve(self):
        return {
            "user_id": self.user_id,
            "texts": [
                self.question,
                self.answer,
            ],
            "metadatas": [
                {
                    "topic": self.topic,
                    "question": self.question,
                    "answer": self.answer,
                    "created_at": self.created_at,
                },
                {
                    "topic": self.topic,
                    "question": self.question,
                    "answer": self.answer,
                    "created_at": self.created_at,
                }
            ]
        }

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

class ChunkType(str, Enum):
    """对话部分类型"""
    USER_INPUT = "user_input"  # 用户输入
    AI_MESSAGE = "ai_message"  # AI 的消息
    AI_DELTA = "ai_delta"  # AI 的增量消息
    MEMORY_RETRIEVE = "memory_retrieve"  # 检索的记忆
    MEMORY_EXTRACT = "memory_extract"  # 提取的记忆
    TITLE_UPDATE = "title_update"  # 标题更新通知

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
    memory: Union[MemoryQA, None] = Field(default=None, description="提取的记忆")

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
                "chunk_type": self.chunk_type.value,
                "input_messages": self.input_messages,
            }
        elif self.chunk_type == ChunkType.AI_DELTA:
            return {
                **common_fields,
                "chunk_type": self.chunk_type.value,
                "output_text": self.output_text,
            }
        elif self.chunk_type == ChunkType.AI_MESSAGE:
            return {
                **common_fields,
                "chunk_type": self.chunk_type.value,
                "output_text": self.output_text,
                "tool_calls": [v.model_dump() for v in self.tool_calls],
            }
        elif self.chunk_type in [ChunkType.MEMORY_EXTRACT, ChunkType.MEMORY_RETRIEVE]:
            return {
                **common_fields,
                "chunk_type": self.chunk_type.value,
                "memory": self.memory.model_dump() if self.memory else None,
            }
        else:
            raise ValueError(f"Invalid chunk type: {self.chunk_type}")
