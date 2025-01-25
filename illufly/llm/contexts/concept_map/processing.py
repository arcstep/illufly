from .storage import ConceptStorage
from .merge_strategies import MergeStrategyRegistry

class ConceptProcessingMachine(StateMachine):
    # 状态定义
    receiving = State('Receiving', initial=True)
    analyzing = State('Analyzing')
    merging = State('Merging')
    updating = State('Updating')
    completed = State('Completed', final=True)
    error = State('Error', final=True)
    
    # 转换定义
    start_analysis = receiving.to(analyzing)
    need_merge = analyzing.to(merging, cond='should_merge')
    direct_update = analyzing.to(updating, unless='should_merge')
    finish_merge = merging.to(updating)
    complete = updating.to(completed)
    
    # 错误处理
    error_transition = (
        receiving.to(error)
        | analyzing.to(error)
        | merging.to(error)
        | updating.to(error)
    )

    def __init__(self, layer_level, merge_registry):
        self.layer_level = layer_level
        self.merge_registry = merge_registry
        self.current_content = None
        super().__init__()

    async def on_enter_analyzing(self):
        """分析阶段的处理逻辑"""
        self.analysis_result = await self.analyze_content(self.current_content)
    
    async def should_merge(self):
        """判断是否需要合并"""
        similar_concepts = await self.find_similar_concepts(self.current_content)
        return len(similar_concepts) > 0
    
    async def on_enter_merging(self):
        """合并阶段的处理逻辑"""
        merge_strategy = await self.determine_merge_strategy()
        self.current_content = await self.merge_registry.execute_merge(
            merge_strategy,
            self.current_content
        )
    
    async def on_enter_updating(self):
        """更新阶段的处理逻辑"""
        await self.update_storage(self.current_content)
        
    def on_enter_error(self):
        """错误处理逻辑"""
        logger.error(f"Layer {self.layer_level} processing error")
    
    async def analyze_content(self, content):
        """分析内容，提取关键信息"""
        # 可以使用LLM进行内容分析
        analysis_result = await self.llm_analyze(content)
        return analysis_result
    
    async def find_similar_concepts(self, content):
        """查找相似概念"""
        storage = ConceptStorage()
        similar = await storage.find_similar_concepts(
            content,
            self.layer_level
        )
        return similar
    
    async def determine_merge_strategy(self) -> str:
        """确定合并策略"""
        if self.layer_level == 0:
            return "absorption"  # L0层主要使用吸收合并
        elif self.layer_level == 1:
            return "fusion"      # L1层主要使用融合合并
        else:
            return "hierarchical"  # 更高层使用层级合并
            
    async def update_storage(self, content):
        """更新存储"""
        storage = ConceptStorage()
        await storage.store_concept(self.layer_level, content)

class LayerProcessor:
    def __init__(self, layer_level, merge_registry):
        self.state_machine = ConceptProcessingMachine(
            layer_level=layer_level,
            merge_registry=merge_registry
        )
        
    async def process(self, content):
        self.state_machine.current_content = content
        
        try:
            # 开始处理流程
            await self.state_machine.start_analysis()
            
            if self.state_machine.current_state == self.state_machine.completed:
                return self.state_machine.current_content
            else:
                raise ProcessingError("Processing incomplete")
                
        except Exception as e:
            await self.state_machine.error_transition()
            raise ProcessingError(f"Processing failed: {str(e)}")

class LayerCommunicator:
    def __init__(self):
        self.processors = {}
        
    def register_processor(self, level, processor):
        self.processors[level] = processor
        
    async def notify_next_layer(self, level, content):
        if next_processor := self.processors.get(level + 1):
            await next_processor.process(content)
