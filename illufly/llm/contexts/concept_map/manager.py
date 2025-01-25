from typing import Dict, Any
import asyncio
from .merge_strategies import MergeStrategyRegistry
from .processing import LayerProcessor, LayerCommunicator
from .storage import ConceptRetriever

LAYER_CONFIGS = {
    0: {
        "name": "raw_layer",
        "merge_strategy": "absorption",
        "similarity_threshold": 0.95,  # 相似度要求最高
    },
    1: {
        "name": "concept_layer", 
        "merge_strategy": "fusion",
        "similarity_threshold": 0.85,
    },
    2: {
        "name": "theme_layer",
        "merge_strategy": "hierarchical", 
        "similarity_threshold": 0.75,  # 相似度要求较低
    }
}

class ConceptMapManager:
    def __init__(self, layer_configs: Dict[int, Dict] = LAYER_CONFIGS):
        self.layer_configs = layer_configs
        self.merge_registry = MergeStrategyRegistry()
        self.communicator = LayerCommunicator()
        self.processors: Dict[int, LayerProcessor] = {}
        self.retriever = ConceptRetriever()
        
        # 初始化合并策略
        self._init_merge_strategies()
        # 初始化层级处理器
        self._init_processors()
        
    def _init_merge_strategies(self):
        """初始化各种合并策略"""
        self.merge_registry.register("absorption", AbsorptionMerge())
        self.merge_registry.register("fusion", FusionMerge())
        self.merge_registry.register("hierarchical", HierarchicalMerge())
        
    def _init_processors(self):
        """初始化各层处理器"""
        for level, config in self.layer_configs.items():
            processor = LayerProcessor(level, self.merge_registry)
            self.processors[level] = processor
            self.communicator.register_processor(level, processor)
            
    async def process_new_content(self, content: Any):
        """处理新内容"""
        try:
            # 从L0开始处理
            result = await self.processors[0].process(content)
            # 触发后续层级处理
            asyncio.create_task(self._process_higher_layers(0, result))
            return result
        except Exception as e:
            logger.error(f"Content processing failed: {str(e)}")
            raise
            
    async def _process_higher_layers(self, current_level: int, content: Any):
        """处理更高层级"""
        try:
            next_level = current_level + 1
            if next_level in self.processors:
                result = await self.processors[next_level].process(content)
                # 继续触发更高层处理
                await self._process_higher_layers(next_level, result)
        except Exception as e:
            logger.error(f"Higher layer processing failed at L{next_level}: {str(e)}")
            
    async def query_concepts(self, query: str, context: Optional[Dict] = None):
        """查询概念"""
        return await self.retriever.retrieve(query, context)
        
    async def get_processing_status(self):
        """获取处理状态"""
        status = {}
        for level, processor in self.processors.items():
            status[level] = {
                "state": processor.state_machine.current_state.id,
                "content_count": await self._get_layer_content_count(level)
            }
        return status