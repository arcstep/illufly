from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union

class ChatBase(ABC):
    """Base Chat Generator"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @abstractmethod
    async def generate(self, messages: Union[str, List[Dict[str, Any]]], **kwargs):
        """异步生成响应"""
        pass
