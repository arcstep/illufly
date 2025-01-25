from abc import ABC, abstractmethod
from typing import Any, Dict, List

class BaseMergeStrategy(ABC):
    @abstractmethod
    async def merge(self, current_content: Any, existing_content: Any) -> Any:
        """执行合并操作"""
        pass

class AbsorptionMerge(BaseMergeStrategy):
    """吸收合并：将新内容合并到已有概念中"""
    async def merge(self, current_content, existing_content):
        # 使用LLM进行内容合并
        merged_content = await self.llm_merge(
            primary=existing_content,
            secondary=current_content
        )
        return merged_content

class FusionMerge(BaseMergeStrategy):
    """融合合并：创建新的概念"""
    async def merge(self, current_content, existing_content):
        # 使用LLM创建新概念
        new_concept = await self.llm_create_concept(
            content_a=current_content,
            content_b=existing_content
        )
        return new_concept

class HierarchicalMerge(BaseMergeStrategy):
    """层级合并：将多个概念合并为更高层概念"""
    async def merge(self, current_content, existing_contents: List):
        # 使用LLM提取高层概念
        higher_concept = await self.llm_extract_higher_concept(
            [current_content, *existing_contents]
        )
        return higher_concept

class MergeStrategyRegistry:
    def __init__(self):
        self.strategies: Dict[str, BaseMergeStrategy] = {}
        
    def register(self, name: str, strategy: BaseMergeStrategy):
        """注册合并策略"""
        self.strategies[name] = strategy
        
    async def execute_merge(self, strategy_name: str, current_content: Any, 
                          existing_content: Any = None) -> Any:
        """执行指定的合并策略"""
        if strategy := self.strategies.get(strategy_name):
            return await strategy.merge(current_content, existing_content)
        raise ValueError(f"Unknown merge strategy: {strategy_name}")