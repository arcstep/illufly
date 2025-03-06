from pydantic import BaseModel, Field
from datetime import datetime

import uuid

CHAT_THREAD_NO_RECENT = "chat_thread_no_recent"

DOMAIN_MODEL = "memory_domain"
TOPIC_MODEL = "memory_topic"
CHUNK_MODEL = "memory_chunk"

class MemoryDomain(BaseModel):
    user_id: str = Field(..., description="用户ID")
    parent_link_name: str = Field(default="_", description="父级链接")
    link_name: str = Field(default="_", description="链接名称")

    @classmethod
    def get_user_prefix(cls, user_id: str):
        return f"mem_domain:{user_id}"

    @classmethod
    def get_key(cls, user_id: str, link_name: str = None, parent_link_name: str = None):
        return f"{cls.get_user_prefix(user_id)}:{parent_link_name or '_'}:{link_name or '_'}"

class MemoryTopic(BaseModel):
    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="线程ID")
    topic_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex), description="主题ID")
    title: str = Field(default="New Topic", description="主题标题")
    summary: str = Field(default="", description="主题摘要")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="创建时间")

    @classmethod
    def get_user_prefix(cls, user_id: str, thread_id: str = None):
        return f"mem_topic:{user_id}:{thread_id or ''}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str, topic_id: str):
        return f"{cls.get_user_prefix(user_id, thread_id)}:{topic_id}"

class MemoryChunk(BaseModel):
    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="线程ID")
    topic_id: str = Field(default="_", description="主题ID")
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex), description="记忆片段ID")
    question: str = Field(..., description="问题")
    answer: str = Field(..., description="答案")
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp(), description="创建时间")

    @classmethod
    def get_user_prefix(cls, user_id: str, thread_id: str = None, topic_id: str = None):
        return f"mem_chunk:{user_id}:{thread_id or CHAT_THREAD_NO_RECENT}:{topic_id or ''}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str, topic_id: str, chunk_id: str):
        return f"{cls.get_user_prefix(user_id, thread_id, topic_id)}:{chunk_id}"

