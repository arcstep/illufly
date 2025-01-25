from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseContext():
    """上下文环境"""
    def __init__(self, **kwargs):
        pass

    def handle_input_messages(self, messages: List[Dict[str, Any]]):
        """处理输入消息"""
        pass

    def handle_output_messages(self, messages: List[Dict[str, Any]]):
        """处理输出消息"""
        pass
