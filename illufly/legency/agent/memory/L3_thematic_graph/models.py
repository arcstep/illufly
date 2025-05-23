from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from ..L2_concept import Concept
from ..utils import generate_id, generate_key
from ..types import MemoryType
class ThematicGraph(BaseModel):
    """L3: 主题概念图

    主题概念图，通常用于保存一个 thread_id 的所有主题概念图。
    概念图应当包含多个概念及其之间的关系，可导出为一个 DOT 语法的概念图说明。
    概念图是基于一次对话的概念认知梳理，是用户认知管理中最核心的结构。
    """
    theme_id: str = Field(default=None, description="主题ID，如果为None，则自动生成")
    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    theme_name: str = Field(..., description="主题名称")
    concepts: List[str] = Field(..., description="概念ID列表")
    relations: List[Dict] = Field(
        default_factory=list,
        description="概念间的关系"
    )
    summary: str = Field(..., description="主题摘要")
    parent_theme: Optional[str] = Field(default=None, description="父主题ID")
    sub_themes: List[str] = Field(default_factory=list, description="子主题ID列表")

    def model_post_init(self, __context) -> None:
        """自动生成theme_id"""
        self.theme_id = generate_id()

    def to_dot(self) -> str:
        """导出为 DOT 语法的概念图说明"""
        dot_content = ["digraph G {"]
        
        # 添加节点
        for concept_id in self.concepts:
            dot_content.append(f'    "{concept_id}" [label="{concept_id}"];')
            
        # 添加关系
        for relation in self.relations:
            source = relation["source"]
            target = relation["target"]
            rel_type = relation["type"]
            dot_content.append(
                f'    "{source}" -> "{target}" [label="{rel_type}"];'
            )
            
        dot_content.append("}")
        return "\n".join(dot_content)

    def update_with_new_concepts(self, new_concepts: List[Concept]) -> None:
        """增量更新概念图"""
        pass
        
    def resolve_conflicts(self) -> None:
        """处理概念冲突"""
        pass

    @property
    def key(self):
        """生成主题概念图的唯一键"""
        return generate_key(MemoryType.THEMATIC_GRAPH, self.user_id, self.thread_id, self.theme_id)

    @property
    def parent_key(self):
        """生成主题概念图的父键"""
        return generate_key(MemoryType.THEMATIC_GRAPH, self.user_id, self.thread_id)