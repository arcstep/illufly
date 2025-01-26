from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from ..L1_facts import FactQueue
from ..L2_concept import Concept

class ThematicGraph(BaseModel):
    """L3: 主题概念图

    主题概念图，通常用于保存一个 thread_id 的所有主题概念图。
    概念图应当包含多个概念及其之间的关系，可导出为一个 DOT 语法的概念图说明。
    概念图是基于一次对话的概念认知梳理，是用户认知管理中最核心的结构。
    """
    theme_id: str
    theme_name: str
    concepts: List[str] = Field(..., description="概念ID列表")
    relations: List[Dict] = Field(
        default_factory=list,
        description="概念间的关系"
    )
    summary: str = Field(..., description="主题摘要")
    parent_theme: Optional[str] = None  # 父主题ID
    sub_themes: List[str] = Field(default_factory=list)  # 子主题ID列表

    def to_dot(self) -> str:
        """导出为 DOT 语法的概念图说明"""
        dot_content = ""
        for concept in self.concepts:
            dot_content += f"{concept.concept_id} [label=\"{concept.concept_name}\"];\n"
        return f"digraph G {{\n{dot_content}\n}}"

    def update_with_new_concepts(self, new_concepts: List[Concept]) -> None:
        """增量更新概念图"""
        pass
        
    def resolve_conflicts(self) -> None:
        """处理概念冲突"""
        pass

class CoreView(BaseModel):
    """L4: 中心观点

    每个中心观点对应一个概念图，每个概念图可产生多个中心观点。
    中心观点是对概念图的特定场景解释，是基于概念图特定路径的看法。
    """
    view_id: str
    theme_id: str  # 关联的主题ID
    statement: str  # 观点陈述，对概念图做
    scope: Dict = Field(..., description="适用范围")
    dependencies: List[str] = Field(
        default_factory=list,
        description="依赖的其他观点ID"
    )
    valid_until: Optional[datetime] = None

