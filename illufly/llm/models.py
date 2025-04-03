from pydantic import BaseModel, Field, computed_field, model_validator
from datetime import datetime
from typing import Dict, Any, List, Union, Optional

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
    TOOL_RESULT = "tool_result"  # 工具调用结果

class DialougeChunk(BaseModel):
    """对话块，用于记录对话的各个部分"""
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
    
    # 主键字段
    user_id: Union[str, None] = Field(default=None, description="用户ID")
    thread_id: Union[str, None] = Field(default=None, description="对话线程ID")
    dialouge_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="对话片段ID")

    # 基础字段
    chunk_type: ChunkType = Field(..., description="对话片段类型")
    role: Optional[str] = Field(default=None, description="对话角色")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="创建时间")
    
    # 输入/输出内容（根据类型选择性填写）
    input_messages: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="用户输入的消息列表")
    output_text: Optional[str] = Field(default="", description="AI 的输出内容")
    
    # 工具调用相关
    tool_calls: Optional[List[ToolCalling]] = Field(default=None, description="工具调用列表")
    tool_id: Optional[str] = Field(default=None, description="工具调用ID")
    tool_name: Optional[str] = Field(default=None, description="工具名称")
    
    # 记忆相关
    memory: Optional[MemoryQA] = Field(default=None, description="记忆问答对")

    def model_dump(self):
        common_fields = {
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "dialouge_id": self.dialouge_id,
            "created_at": self.created_at
        }
        
        if self.chunk_type == ChunkType.USER_INPUT:
            return {
                **common_fields,
                "chunk_type": self.chunk_type.value,
                "input_messages": self.input_messages
            }
        elif self.chunk_type == ChunkType.AI_DELTA:
            return {
                **common_fields,
                "chunk_type": self.chunk_type.value,
                "output_text": self.output_text
            }
        elif self.chunk_type == ChunkType.AI_MESSAGE:
            result = {
                **common_fields,
                "chunk_type": self.chunk_type.value,
            }
            
            if self.output_text:
                result["output_text"] = self.output_text
                
            if self.tool_calls:
                result["tool_calls"] = [tc.model_dump() for tc in self.tool_calls]
                
            return result
        elif self.chunk_type == ChunkType.MEMORY_RETRIEVE or self.chunk_type == ChunkType.MEMORY_EXTRACT:
            return {
                **common_fields,
                "chunk_type": self.chunk_type.value,
                "memory": self.memory.model_dump() if self.memory else None,
            }
        elif self.chunk_type == ChunkType.TOOL_RESULT:
            result = {
                **common_fields,
                "chunk_type": self.chunk_type.value,
                "output_text": self.output_text,
            }
            
            if self.tool_id:
                result["tool_id"] = self.tool_id
                
            if self.tool_name:
                result["tool_name"] = self.tool_name
                
            return result
        elif self.chunk_type == ChunkType.TITLE_UPDATE:
            return {
                **common_fields,
                "chunk_type": self.chunk_type.value,
                "output_text": self.output_text
            }
        else:
            raise ValueError(f"Invalid chunk type: {self.chunk_type}")
