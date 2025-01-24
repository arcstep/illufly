from abc import ABC, abstractmethod
from typing import Dict, Any, List

class ContextBase(ABC):
    """上下文环境"""
    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def handle_input_messages(self, messages: List[Dict[str, Any]]):
        """处理单条消息"""
        pass

    @abstractmethod
    def handle_output_messages(self, messages: List[Dict[str, Any]]):
        """处理单条消息"""
        pass
