from datetime import datetime
from typing import List, Dict
from pydantic import BaseModel, Field, field_validator

class FactSummary(BaseModel):
    """L1: 单个事实摘要表示，从L0单次对话中提炼的事实

    从单词对话中提炼的事实，应当根据领域、用户偏好、观点倾向等进行提炼。
    """
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

class FactQueue(BaseModel):
    """L1: 事实摘要队列，提炼L0前检查是否需要提炼，提炼后合并到队列
    
    事实队列，通常用于保存一个 thread_id 的所有的事实摘要。
    """
    thread_id: str = Field(..., description="对话ID")
    facts: Dict[str, List[FactSummary]] = Field(
        default_factory=dict,
        description="按title分组的事实摘要列表，每组按时间排序"
    )
    
    def add_fact(self, fact: FactSummary):
        """添加新的事实摘要"""
        if fact.title not in self.facts:
            self.facts[fact.title] = []
        self.facts[fact.title].append(fact)
        # 按时间戳排序
        self.facts[fact.title].sort(key=lambda x: x.timestamp)
        
    def get_latest_facts(self) -> Dict[str, FactSummary]:
        """获取每个名称的最新事实摘要"""
        return {
            name: facts[-1] 
            for name, facts in self.facts.items()
            if facts
        }

    def merge_similar_facts(self) -> None:
        """合并相似事实，避免冗余"""
        pass
        
    def prune_outdated_facts(self) -> None:
        """清理过期事实"""
        pass
