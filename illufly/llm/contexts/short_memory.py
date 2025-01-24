from .base import ContextBase
from typing import Dict, Any, List

class ShortMemoryContext(ContextBase):
    """短期记忆

    短期记忆是基于多轮对话的上下文环境，用于存储最近一轮对话的上下文环境。
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.history = []
        self.latest_round = 10

    def handle_input_messages(self, messages: List[Dict[str, Any]]):
        """处理单条消息"""

        self.history.extend(messages)
        return self.history[-self.latest_round:]

    def handle_output_messages(self, messages: List[Dict[str, Any]]):
        """处理单条消息"""

        self.history.extend(messages)
