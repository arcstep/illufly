from pydantic import BaseModel, Field
from datetime import datetime
from typing import Union, Tuple, Dict, Any
import uuid
from ...rocksdb import IndexedRocksDB

class MemoryMessage(BaseModel):
    """简单消息"""
    @classmethod
    def create(cls, data: Union[str, Tuple[str, str], Dict[str, Any], "HistoryMessage"]):
        if isinstance(data, str):
            return cls(role="user", content=data)
        elif isinstance(data, tuple):
            return cls(role="assistant" if data[0] == "ai" else data[0], content=data[1])
        elif isinstance(data, HistoryMessage):
            return data
        return cls(**data)
    
    role: str = Field(
        ..., 
        description="消息角色：user/assistant/system/tool",
        pattern="^(user|assistant|system|tool)$"
    )
    content: Union[str, Dict[str, Any]] = Field(..., description="消息内容")

class HistoryMessage(MemoryMessage):
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
    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="消息ID")
    qa_type: str = Field(..., description="问答类型", pattern="^(question|answer)$")
    message_type: str = Field(..., description="消息类型", pattern="^(text|image|audio|video|file|text_chunk|end)$")
    favorite_id: Union[str, None] = Field(default=None, description="收藏ID")
    created_at: datetime = Field(default_factory=datetime.now, description="消息开始构造时间")
    completed_at: datetime = Field(default=None, description="消息完成时间")
