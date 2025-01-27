from datetime import datetime
from typing import List, Dict
from pydantic import BaseModel, Field, field_validator

from ..utils import generate_id

class Fact(BaseModel):
    """L1: 单个事实摘要表示，从L0单次对话中提炼的事实

    从单词对话中提炼的事实，应当根据领域、用户偏好、观点倾向等进行提炼。
    """
    fact_id: str = Field(default=None, description="事实ID，如果为None，则自动生成")
    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    title: str = Field(..., description="事实摘要的唯一标识名称，不超过30个字符")
    content: str = Field(..., description="摘要内容，不超过200个字符")
    timestamp: datetime = Field(default_factory=datetime.now)
    source_chat_threads: List[str] = Field(..., description="来源对话 thread_id 列表")
    window_start: datetime  # 滚动窗口起始时间
    window_end: datetime    # 滚动窗口结束时间

    @field_validator('title')
    def validate_title_length(cls, v):
        if len(v) > 30:
            raise ValueError("标题长度不能超过30个字符")
        return v
    
    @field_validator('content')
    def validate_content_length(cls, v):
        if len(v) > 200:
            raise ValueError("内容长度不能超过200个字符")
        return v

    def model_post_init(self, __context) -> None:
        """自动生成fact_id"""
        self.fact_id = generate_id("fact", self.user_id, self.thread_id)
