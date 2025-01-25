from .base import BaseContext
from typing import Dict, Any, List

class ShortMemoryContext(BaseContext):
    """短期记忆

    短期记忆是基于多轮对话的上下文环境，用于存储最近一轮对话的上下文环境。
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.history = []
        self.latest_round = 10

    def handle_input_messages(self, messages: List[Dict[str, Any]]):
        """根据输入消息，提取历史记录"""

        self.history.extend(messages)
        return self.history[-self.latest_round:]

    def handle_output_messages(self, messages: List[Dict[str, Any]]):
        """根据输出消息，更新历史记录"""

        self.history.extend(messages)
