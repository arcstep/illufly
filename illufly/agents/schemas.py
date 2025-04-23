from pydantic import BaseModel, Field, computed_field, model_validator
from datetime import datetime
from typing import Dict, Any, List, Union, Optional

from enum import Enum
import uuid
import time
import hashlib
import json

from voidring import IndexedRocksDB

class MemoryQA(BaseModel):
    """
    使用主题、问题、答案这样的标准形式来表示用户反馈或用户经验。
    """
    user_id: Union[str, None] = Field(default=None, description="用户ID")
    topic: str = Field(default="", description="话题")
    question: str = Field(default="", description="问题")
    answer: str = Field(default="", description="答案")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="创建时间")
    distance: Optional[float] = Field(default=None, description="搜索距离，越小越相似")
    memory_id: str = Field(default_factory=lambda: uuid.uuid4().hex, description="记忆唯一ID")

    @classmethod
    def register_indexes(cls, db: IndexedRocksDB):
        db.register_collection(cls.__name__, cls)
        db.register_index(cls.__name__, cls, "topic")
        db.register_index(cls.__name__, cls, "created_at")

    @classmethod
    def get_prefix(cls, user_id: str):
        return f"mem-{user_id}"

    @classmethod
    def get_key(cls, user_id: str, memory_id: str):
        return f"{cls.get_prefix(user_id)}-{memory_id}"

    def to_retrieve(self):
        return {
            "user_id": self.user_id,
            "texts": [self.question, self.answer],
            "metadatas": [
                {
                    "topic": self.topic,
                    "question": self.question,
                    "answer": self.answer,
                    "created_at": self.created_at,
                    "memory_id": self.memory_id
                },
                {
                    "topic": self.topic,
                    "question": self.question,
                    "answer": self.answer,
                    "created_at": self.created_at,
                    "memory_id": self.memory_id
                }
            ],
            "ids": [self.memory_id, self.memory_id]
        }

class Thread(BaseModel):
    """连续对话跟踪，包含多个对话轮次"""
    @classmethod
    def register_indexes(cls, db: IndexedRocksDB):
        db.register_collection(cls.__name__, cls)
        db.register_index(cls.__name__, cls, "created_at")

    @classmethod
    def get_prefix(cls, user_id: str):
        return f"thread-{user_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str):
        return f"{cls.get_prefix(user_id)}-{thread_id}"

    user_id: Union[str, None] = Field(default=None, description="用户ID")
    thread_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="对话线程ID")
    title: str = Field(default="", description="连续对话标题")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="对话创建时间")
    dialogue_count: int = Field(default=0, description="对话轮次计数")

class ToolCall(BaseModel):
    tool_id: str = Field(default="", description="工具ID")
    name: str = Field(default="", description="工具名称")
    arguments: str = Field(default="", description="工具参数")

class ChunkType(str, Enum):
    """对话块类型"""
    USER_INPUT = "user_input"  # 用户输入块
    AI_MESSAGE = "ai_message"  # AI完整回复块
    AI_DELTA = "ai_delta"      # AI增量回复片段
    MEMORY_RETRIEVE = "memory_retrieve"  # 检索的记忆块
    MEMORY_EXTRACT = "memory_extract"    # 提取的记忆块
    TITLE_UPDATE = "title_update"        # 标题更新通知块
    TOOL_RESULT = "tool_result"          # 工具调用结果块

class Dialogue(BaseModel):
    """对话轮次，一轮完整的交互，包含多个对话块"""
    @classmethod
    def register_indexes(cls, db: IndexedRocksDB):
        db.register_collection(cls.__name__, cls)
        db.register_index(cls.__name__, cls, "created_at")
    
    @classmethod
    def get_prefix(cls, user_id: str, thread_id: str):
        return f"dlg-{user_id}-{thread_id}"
    
    @classmethod
    def get_key(cls, user_id: str, thread_id: str, dialogue_id: str):
        return f"{cls.get_prefix(user_id, thread_id)}-{dialogue_id}"
    
    # 主键字段
    user_id: Union[str, None] = Field(default=None, description="用户ID")
    thread_id: Union[str, None] = Field(default=None, description="对话线程ID")
    dialogue_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="对话轮次ID")
    
    # 基础字段
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="创建时间")
    updated_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="更新时间")
    
    # 对话内容摘要
    user_content: str = Field(default="", description="用户输入内容摘要")
    ai_content: str = Field(default="", description="AI回复内容摘要")
    
    # 统计信息
    chunk_count: int = Field(default=0, description="对话块计数")
    
    # 处理状态
    completed: bool = Field(default=False, description="对话是否已完成")

class DialogueChunk(BaseModel):
    """对话块，一次完整的输入或输出，可能包含多个增量片段"""
    @classmethod
    def register_indexes(cls, db: IndexedRocksDB):
        db.register_collection(cls.__name__, cls)
        db.register_index(cls.__name__, cls, "created_at")
    
    @classmethod
    def get_prefix(cls, user_id: str, thread_id: str, dialogue_id: str):
        return f"chunk-{user_id}-{thread_id}-{dialogue_id}"
    
    @classmethod
    def get_key(cls, user_id: str, thread_id: str, dialogue_id: str, chunk_id: str):
        return f"{cls.get_prefix(user_id, thread_id, dialogue_id)}-{chunk_id}"
    
    # 主键字段
    user_id: Union[str, None] = Field(default=None, description="用户ID")
    thread_id: Union[str, None] = Field(default=None, description="对话线程ID")
    dialogue_id: Union[str, None] = Field(default=None, description="对话轮次ID")
    chunk_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="对话块ID")

    # 基础字段
    chunk_type: ChunkType = Field(..., description="对话块类型")
    role: Optional[str] = Field(default=None, description="对话角色")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="创建时间")
    
    # 序列号，用于对增量片段排序
    sequence: int = Field(default=0, description="序列号，用于排序")
    
    # 内容字段
    content: Optional[str] = Field(default="", description="显示内容")
    
    # 输入/输出内容（根据类型选择性填写）
    input_messages: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="用户输入的消息列表")
    patched_messages: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="补充过的消息列表")
    output_text: Optional[str] = Field(default="", description="AI的输出内容")
    
    # 工具调用相关
    tool_calls: Optional[List[ToolCall]] = Field(default=None, description="工具调用列表")
    tool_id: Optional[str] = Field(default=None, description="工具调用ID")
    tool_name: Optional[str] = Field(default=None, description="工具名称")
    
    # 记忆相关
    memory: Optional[MemoryQA] = Field(default=None, description="记忆问答对")
    
    # 是否为最终内容
    is_final: bool = Field(default=False, description="是否为最终内容，用于区分增量和完整内容")

    def model_dump(self):
        """
        统一格式化对话块，确保所有类型都包含前端所需的基本字段
        返回的字典必须包含：
        - 所有基本信息字段(user_id, thread_id, dialogue_id, chunk_id, created_at, chunk_type)
        - role: 对话角色
        - content: 前端显示的内容
        - 其他特有字段
        """
        # 基础字段，所有消息类型共有
        common_fields = {
            "chunk_type": self.chunk_type.value,
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "dialogue_id": self.dialogue_id,
            "chunk_id": self.chunk_id,
            "created_at": self.created_at,
            "sequence": self.sequence,
            "is_final": self.is_final
        }
        
        # 尝试使用提供的content，如果没有则根据类型生成
        content = self.content
        
        # 为不同类型的消息定制处理逻辑
        if self.chunk_type == ChunkType.USER_INPUT:
            # 用户输入
            content = self.input_messages[-1].get("content", json.dumps(self.input_messages, ensure_ascii=False))
                
            return {
                **common_fields,
                "role": self.role or "user",
                "content": content,
                "input_messages": self.input_messages
            }
            
        elif self.chunk_type == ChunkType.AI_DELTA:
            # AI增量响应
            return {
                **common_fields,
                "role": self.role or "assistant",
                "content": content or self.output_text or "",
                "output_text": self.output_text
            }
            
        elif self.chunk_type == ChunkType.AI_MESSAGE:
            # AI完整消息
            if not content:
                content = self.output_text or ""
                
                # 检查是否有工具调用
                if self.tool_calls and len(self.tool_calls) > 0:
                    tool_info = ", ".join([f"{tc.name}" for tc in self.tool_calls])
                    content = f"工具调用: {tool_info}" if not content else content
                
            result = {
                **common_fields,
                "role": self.role or "assistant",
                "content": content,
            }
            
            if self.output_text:
                result["output_text"] = self.output_text
                
            if self.tool_calls:
                result["tool_calls"] = [tc.model_dump() for tc in self.tool_calls]
                
            return result
            
        elif self.chunk_type in [ChunkType.MEMORY_RETRIEVE, ChunkType.MEMORY_EXTRACT]:
            # 记忆相关消息
            if not content and self.memory:
                prefix = "记忆" if self.chunk_type == ChunkType.MEMORY_RETRIEVE else "提取记忆"
                content = f"{prefix}: {self.memory.topic}/{self.memory.question}"
            
            return {
                **common_fields,
                "role": self.role or "assistant", 
                "content": content,
                "memory": self.memory.model_dump() if self.memory else None,
            }
            
        elif self.chunk_type == ChunkType.TOOL_RESULT:
            # 工具调用结果
            return {
                **common_fields,
                "role": self.role or "tool",
                "content": content or self.output_text or "",
                "output_text": self.output_text,
                "name": self.tool_name or "",
                "tool_call_id": self.tool_id or "",
                "tool_id": self.tool_id,
                "tool_name": self.tool_name,
            }
            
        elif self.chunk_type == ChunkType.TITLE_UPDATE:
            # 标题更新通知
            return {
                **common_fields,
                "role": self.role or "system",
                "content": content or self.output_text or "",
                "output_text": self.output_text
            }
            
        else:
            raise ValueError(f"Invalid chunk type: {self.chunk_type}")
