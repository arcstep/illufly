from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union

from ..call import RemoteServer
from ..mq import Publisher, StreamingBlock, BlockType, TextChunk

class ChatBase(RemoteServer, ABC):
    """Base Chat Service"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @abstractmethod
    async def _async_generate_from_llm(self, messages: Union[str, List[Dict[str, Any]]], thread_id: str, publisher: Publisher, **kwargs):
        """要求在子类中实现"""
        pass

    async def _async_handler(self, messages: Union[str, List[Dict[str, Any]]], thread_id: str, publisher: Publisher, **kwargs):
        """转换提问的问题"""
        return await self._async_generate_from_llm(messages, thread_id, publisher, **kwargs)
