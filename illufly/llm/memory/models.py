from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

from .L0_dialogue import Message, Dialogue
from .L1_facts import Fact
from .L2_concept import Concept
from .L3_thematic_graph import ThematicGraph
from .L4_core_view import CoreView

class TaskStatus(str, Enum):
    PENDING = "pending"      # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"         # 处理失败
    TIMEOUT = "timeout"       # 处理超时

class ProcessingTask(BaseModel):
    """处理任务"""
    task_id: str
    level: str  # fact, concept, theme, view
    thread_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    payload: Dict
    error: Optional[str] = None
    retry_count: int = 0

class ConversationCognitive(BaseModel):
    """某次连续对话的用户认知

    在一次连续对话中包含的每一轮的对话数据清单、事实清单、概念清单、主题概念图清单、核心观点清单等。
    """
    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    dialogues: List[Dialogue] = Field(default_factory=list, description="原始对话")
    concepts: List[Concept] = Field(default_factory=list, description="概念清单")
    themes: List[ThematicGraph] = Field(default_factory=list, description="主题图")
    views: List[CoreView] = Field(default_factory=list, description="中心观点")

class FinalCognitive(BaseModel):
    """最终的用户认知

    基于多轮对话迭代的用户最终认知。
    """
    user_id: str = Field(..., description="用户ID")
    facts: Dict[str, Fact]   # 事实清单
    concepts: Dict[str, Concept]    # 概念清单
    themes: Dict[str, ThematicGraph]  # 主题图
    views: Dict[str, CoreView]      # 中心观点
    
    class ConfigDict:
        arbitrary_types_allowed = True

    async def merge_conversation_cognitive(
        self, 
        conv_cognitive: ConversationCognitive
    ) -> None:
        """合并新的会话认知"""
        pass
        
    def evaluate_cognitive_changes(self) -> Dict:
        """评估认知变化"""
        pass
