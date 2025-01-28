from datetime import datetime
from typing import Dict, List, Union, Any, Tuple
from pydantic import BaseModel, Field, computed_field

import uuid

from ..utils import generate_id, generate_key
from ..types import MemoryType

class Message(BaseModel):
    """原始消息

    用于格式化，在内存中交换。
    """
    role: str = Field(
        ..., 
        description="消息角色：user/assistant/system/tool",
        pattern="^(user|assistant|system|tool)$"
    )
    content: Union[str, Dict[str, Any]] = Field(..., description="消息内容")
    timestamp: datetime = Field(default_factory=datetime.now)

    @property
    def message(self):
        return self.model_dump(exclude={"timestamp"})
    
    @classmethod
    def create(cls, data: Union[str, Tuple[str, str], Dict[str, Any], "Message"]):
        if isinstance(data, str):
            return cls(role="user", content=data)
        elif isinstance(data, tuple):
            return cls(role="assistant" if data[0] == "ai" else data[0], content=data[1])
        elif isinstance(data, Message):
            return data
        return cls(**data)

class Thread(BaseModel):
    """连续对话跟踪"""
    user_id: str = Field(..., description="用户ID")
    thread_id: Union[str, None] = Field(default=None, description="对话ID")
    title: str = Field(default="", description="对话标题")
    description: str = Field(default="", description="对话描述")
    created_at: datetime = Field(default_factory=datetime.now, description="对话创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="对话更新时间")

    def model_post_init(self, __context) -> None:
        """在模型初始化后执行"""
        if not self.thread_id:
            self.thread_id = uuid.uuid4().hex

    @property
    def key(self):
        return generate_key(MemoryType.THREAD, self.user_id, self.thread_id)

    @property
    def parent_key(self):
        return generate_key(MemoryType.THREAD, self.user_id)

class QA(BaseModel):
    """L0: 单次对话

    持久化保存。
    每次问答都通过 messages 向AI发送了完整的上下文信息。
    通常情况下，我们都需要对本轮对话做摘要处理，以便于后续提取事实和概念。

    必要的构建要求：
        - user_id
        - thread_id
        - messages
    """
    qa_id: str = Field(default=None, description="对话ID，如果为None，则自动生成")
    level: str = Field(default="L0", description="对话层级")
    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    messages: List[Union[Message, Tuple[str, str], Dict[str, Any], str]] = Field(..., description="符合LLM标准的用户与AI的问答消息列表，包括系统提示语、用户输入、AI输出等")
    summary: List[Message] = Field(
        default=[],  # 先设置空列表作为默认值
        description="本轮对话摘要，一般是精简后的问答对消息"
    )
    request_time: datetime = Field(default_factory=datetime.now)
    response_time: datetime = Field(default_factory=datetime.now)
    used_time: float = Field(
        default=0.0,  # 先设置默认值
        description="本轮对话耗时"
    )
    usage: Dict[str, float] = Field(
        default_factory=dict, 
        description="本轮对话的token使用情况"
    )

    @classmethod
    def generate_parent_key(cls, user_id: str, thread_id: str):
        """用于 rocksdb 列举所有键值的 key"""
        return generate_key(MemoryType.QA, user_id, thread_id)

    @property
    def key(self):
        """用于 rocksdb 保存的 key"""
        return generate_key(self.generate_parent_key(self.user_id, self.thread_id), self.qa_id)

    @property
    def question(self):
        for m in self.messages:
            if m.role == "user":
                return m.content
        return ""

    @property
    def answer(self):
        for m in reversed(self.messages):
            if m.role == "assistant":
                return m.content
        return ""

    @property
    def qa_message(self):
        if self.summary:
            return [m.message for m in self.summary]
        
        return [
            {
                "role": "user",
                "content": self.question
            },
            {
                "role": "assistant",
                "content": self.answer
            }
        ]

    def model_post_init(self, __context) -> None:
        """在模型初始化后执行"""
        if self.used_time == 0.0:
            self.used_time = (self.response_time - self.request_time).total_seconds()

        # 如果没有提供qa_id，则自动生成
        if not self.qa_id:
            self.qa_id = generate_id()
        
        self.messages = [Message.create(m) for m in self.messages]

