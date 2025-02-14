from datetime import datetime
from typing import Dict, List, Union, Any, Tuple
from pydantic import BaseModel, Field, computed_field

import uuid

from ..utils import generate_id, generate_key
from ..types import MemoryType, TaskState

def generate_short_id():
    return uuid.uuid4().hex[:8]

class Message(BaseModel):
    """原始消息
    """
    @classmethod
    def get_thread_prefix(cls, user_id: str, thread_id: str):
        return f"msg-{user_id}-{thread_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str, request_id: str, message_id: str):
        return f"{cls.get_thread_prefix(user_id, thread_id)}-{request_id}-{message_id}"

    @classmethod
    def create(cls, data: Union[str, Tuple[str, str], Dict[str, Any], "Message"]):
        if isinstance(data, str):
            return cls(role="user", content=data)
        elif isinstance(data, tuple):
            return cls(role="assistant" if data[0] == "ai" else data[0], content=data[1])
        elif isinstance(data, Message):
            return data
        return cls(**data)

    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    request_id: str = Field(..., description="对话的请求ID")
    message_id: str = Field(default_factory=generate_short_id, description="消息ID")
    role: str = Field(
        ..., 
        description="消息角色：user/assistant/system/tool",
        pattern="^(user|assistant|system|tool)$"
    )
    content: Union[str, Dict[str, Any]] = Field(..., description="消息内容")
    favorite: Union[str, None] = Field(default=None, description="收藏ID")
    created_at: datetime = Field(default_factory=datetime.now, description="消息开始构造时间")
    completed_at: datetime = Field(default=None, description="消息完成时间")

class Favorite(BaseModel):
    """收藏"""
    @classmethod
    def get_user_prefix(cls, user_id: str):
        return f"fav-{user_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str, favorite_id: str):
        return f"{cls.get_user_prefix(user_id)}-{thread_id}-{favorite_id}"

    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    favorite_id: str = Field(default_factory=generate_short_id, description="收藏ID")
    title: str = Field(default="", description="收藏标题")
    tags: List[str] = Field(default=[], description="收藏标签")
    created_at: datetime = Field(default_factory=datetime.now, description="收藏创建时间")

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

class Thread(BaseModel):
    """连续对话跟踪"""
    @classmethod
    def get_user_prefix(cls, user_id: str):
        return f"thread-{user_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str):
        return f"{cls.get_user_prefix(user_id)}-{thread_id}"

    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(default_factory=generate_short_id, description="对话ID")
    title: str = Field(default="", description="对话标题")
    description: str = Field(default="", description="对话描述")
    created_at: datetime = Field(default_factory=datetime.now, description="对话创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="对话更新时间")
