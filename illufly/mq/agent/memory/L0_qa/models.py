from datetime import datetime
from typing import Dict, List, Union, Any, Tuple
from pydantic import BaseModel, Field, computed_field

from .....rocksdb import IndexedRocksDB
from ..utils import generate_short_id
from ..types import TaskState

class SimpleMessage(BaseModel):
    """简单消息"""
    @classmethod
    def create(cls, data: Union[str, Tuple[str, str], Dict[str, Any], "Message"]):
        if isinstance(data, str):
            return cls(role="user", content=data)
        elif isinstance(data, tuple):
            return cls(role="assistant" if data[0] == "ai" else data[0], content=data[1])
        elif isinstance(data, Message):
            return data
        return cls(**data)
    
    role: str = Field(
        ..., 
        description="消息角色：user/assistant/system/tool",
        pattern="^(user|assistant|system|tool)$"
    )
    content: Union[str, Dict[str, Any]] = Field(..., description="消息内容")

class Message(SimpleMessage):
    """原始消息
    """
    @classmethod
    def get_thread_prefix(cls, user_id: str, thread_id: str):
        return f"msg-{user_id}-{thread_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str, request_id: str, message_id: str):
        return f"{cls.get_thread_prefix(user_id, thread_id)}-{request_id}-{message_id}"

    @classmethod
    def register_indexes(cls, db: IndexedRocksDB):
        db.register_model(cls.__name__, cls)
        db.register_index(cls.__name__, cls, "favorite_id")

    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    request_id: str = Field(..., description="对话的请求ID")
    message_id: str = Field(default_factory=generate_short_id, description="消息ID")
    qa_type: str = Field(..., description="问答类型", pattern="^(question|answer)$")
    message_type: str = Field(..., description="消息类型", pattern="^(text|image|audio|video|file|text_chunk|end)$")
    favorite_id: Union[str, None] = Field(default=None, description="收藏ID")
    created_at: datetime = Field(default_factory=datetime.now, description="消息开始构造时间")
    completed_at: datetime = Field(default=None, description="消息完成时间")

class QA(BaseModel):
    """L0: 一次问答
    """
    @classmethod
    def get_thread_prefix(cls, user_id: str, thread_id: str):
        return f"qa-{user_id}-{thread_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str, request_id: str):
        """用于 rocksdb 保存的 key"""
        return f"{cls.get_thread_prefix(user_id, thread_id)}-{request_id}"

    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    request_id: str = Field(default_factory=generate_short_id, description="对话的请求ID")
    summary: Union[List[Message], None] = Field(
        default=None,  # 先设置空列表作为默认值
        description="本轮对话摘要，一般是精简后的问答对消息"
    )
    task_summarize: TaskState = Field(default=TaskState.TODO, description="摘要任务执行状态")
    task_extract_facts: TaskState = Field(default=TaskState.TODO, description="事实提取任务执行状态")

    def task_summarize_completed(self):
        """摘要任务完成"""
        self.task_summarize = TaskState.COMPLETED

    def task_extract_facts_completed(self):
        """事实提取任务完成"""
        self.task_extract_facts = TaskState.COMPLETED
