from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from ..utils import generate_id

class Concept(BaseModel):
    """L2: 概念节点

    概念节点，通常用于保存一个 thread_id 的所有概念节点。
    概念节点是基于一次对话的概念认知梳理，是用户认知管理中最核心的结构。
    """
    concept_id: str = Field(default=None, description="概念ID，如果为None，则自动生成")
    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    concept_name: str = Field(..., description="概念名称")
    description: str = Field(..., description="概念描述")
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

    def model_post_init(self, __context) -> None:
        """自动生成concept_id"""
        self.concept_id = generate_id("concept", self.user_id, self.thread_id)
