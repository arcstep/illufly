from typing import List, Dict
from pydantic import BaseModel, Field

from .L0_dialogue import Message, Dialogue
from .L1_facts import FactQueue, FactSummary
from .L2_concept import Concept
from .L3_concepts_map import CoreView, ThematicGraph

class ConversationCognitive(BaseModel):
    """某次连续对话的用户认知

    在一次连续对话中包含的每一轮的对话数据清单、事实清单、概念清单、主题概念图清单、核心观点清单等。
    """
    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    dialogues: List[Dialogue] = Field(default_factory=list, description="原始对话")
    facts: FactQueue = Field(..., description="事实清单")
    concepts: List[Concept] = Field(default_factory=list, description="概念清单")
    themes: List[ThematicGraph] = Field(default_factory=list, description="主题图")
    views: List[CoreView] = Field(default_factory=list, description="中心观点")

class FinalCognitive(BaseModel):
    """最终的用户认知

    基于多轮对话迭代的用户最终认知。
    """
    user_id: str = Field(..., description="用户ID")
    facts: Dict[str, FactSummary]   # 事实清单
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
