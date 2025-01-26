from datetime import datetime
from typing import Dict, List, Optional, Union, Set
from pydantic import BaseModel, Field

class Message(BaseModel):
    """原始消息"""
    conversation_id: str = Field(..., description="对话ID")
    thread_id: str = Field(..., description="调用ID")
    role: str = Field(..., description="消息角色：user/assistant")
    content: str = Field(..., description="消息内容")
    timestamp: datetime = Field(default_factory=datetime.now)
    
class Dialogue(BaseModel):
    """对话单元"""
    id: str = Field(..., description="对话唯一标识")
    messages: List[Message]
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
class FactSummary(BaseModel):
    """事实摘要"""
    name: str = Field(..., description="事实摘要的唯一标识名称")
    content: str = Field(..., description="摘要内容")
    timestamp: datetime = Field(default_factory=datetime.now)
    source_dialogues: List[str] = Field(..., description="来源对话ID列表")
    window_start: datetime  # 滚动窗口起始时间
    window_end: datetime    # 滚动窗口结束时间

class FactQueue(BaseModel):
    """事实摘要队列"""
    facts: Dict[str, List[FactSummary]] = Field(
        default_factory=dict,
        description="按name分组的事实摘要列表，每组按时间排序"
    )
    
    def add_fact(self, fact: FactSummary):
        """添加新的事实摘要"""
        if fact.name not in self.facts:
            self.facts[fact.name] = []
        self.facts[fact.name].append(fact)
        # 按时间戳排序
        self.facts[fact.name].sort(key=lambda x: x.timestamp)
        
    def get_latest_facts(self) -> Dict[str, FactSummary]:
        """获取每个名称的最新事实摘要"""
        return {
            name: facts[-1] 
            for name, facts in self.facts.items()
            if facts
        }

class Concept(BaseModel):
    """L2: 概念节点"""
    id: str
    name: str
    description: str
    related_facts: List[str] = Field(default_factory=list)  # 关联的事实摘要ID
    relations: Dict[str, List[str]] = Field(
        default_factory=dict, 
        description="与其他概念的关系：{关系类型: [概念ID]}"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evolution: List[Dict] = Field(
        default_factory=list,
        description="概念认知的演化历史"
    )

class ThematicGraph(BaseModel):
    """L3: 主题概念图"""
    id: str
    name: str
    concepts: List[str] = Field(..., description="概念ID列表")
    relations: List[Dict] = Field(
        default_factory=list,
        description="概念间的关系"
    )
    summary: str = Field(..., description="主题摘要")
    parent_theme: Optional[str] = None  # 父主题ID
    sub_themes: List[str] = Field(default_factory=list)  # 子主题ID列表

class CoreView(BaseModel):
    """L4: 中心观点"""
    id: str
    theme_id: str  # 关联的主题ID
    statement: str  # 观点陈述
    scope: Dict = Field(..., description="适用范围")
    dependencies: List[str] = Field(
        default_factory=list,
        description="依赖的其他观点ID"
    )
    valid_until: Optional[datetime] = None

class CognitiveBridge(BaseModel):
    """认知桥整体状态"""
    dialogues: Dict[str, Dialogue]  # 原始对话
    facts: Dict[str, FactSummary]   # 事实摘要
    concepts: Dict[str, Concept]    # 概念节点
    themes: Dict[str, ThematicGraph]  # 主题图
    views: Dict[str, CoreView]      # 中心观点
    
    class Config:
        arbitrary_types_allowed = True