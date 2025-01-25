from .base import BaseContext
from typing import Dict, Any, List

class StrategyContext(BaseContext):
    """对话策略上下文
    
    根据对话状态调整回复策略
    """
    def __init__(self, strategy_rules: Dict[str, Any], **kwargs):
        super().__init__(**kwargs)
        self.strategy_rules = strategy_rules

    def handle_input_messages(self, messages: List[Dict[str, Any]]):
        """分析对话状态，添加策略提示"""
        state = self._analyze_conversation_state(messages)
        strategy = self._select_strategy(state)
        return [{'role': 'system', 'content': strategy}] + messages 