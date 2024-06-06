from typing import Callable, Optional
from langchain.memory import ConversationBufferMemory
from langchain.memory.chat_memory import BaseChatMemory
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.messages import BaseMessage
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from typing import Any, Dict, Union, List
from copy import deepcopy
from ..config import get_default_session

class MemoryManager:
    """
    实现记忆窗口和持久化捆绑管理。

    默认将记忆存储在内存中，但可以替换为redis存储等持久化方案；
    也支持按对话轮次、Token数、知识图谱等管理短期记忆。
    """

    # 短期记忆管理，用于记忆模板
    _memory: BaseChatMemory
    _memory_dict: dict[str, BaseChatMemory] = {}

    # 记忆存储的回调函数，要求使用 session_id 位置参数
    get_store_factory: Callable[[str], BaseChatMessageHistory]

    def __init__(
        self,
        store_factory: Optional[Callable[[str], BaseChatMessageHistory]] = None,
        memory: Optional[BaseChatMemory] = None
    ) -> None:
        self.get_store_factory = store_factory or self._get_history_in_memory
        self._memory = memory or ConversationBufferWindowMemory(k=20, return_messages=True)

    def get_memory(self, session_id: str=None) -> List[BaseMessage]:
        """返回短期内存记忆"""
        session_id = session_id or get_default_session()

        if session_id in self._memory_dict:
            memory = self._memory_dict[session_id]
            return memory.buffer_as_messages
        else:
            return []

    def get_store(self, session_id: str=None) -> List[BaseMessage]:
        """返回长期记忆存储"""
        session_id = session_id or get_default_session()

        if session_id in self._memory_dict:
            memory = self._memory_dict[session_id]
            return memory.chat_memory.messages
        else:
            return []    

    # 结合 session_id 构造记忆对象
    def get_memory_factory(self, session_id: str=None) -> BaseChatMemory:
        session_id = session_id or get_default_session()

        if session_id not in self._memory_dict:
            store = self.get_store_factory(session_id)
            self._memory_dict[session_id] = deepcopy(self._memory)
            self._memory_dict[session_id].chat_memory = store

        return self._memory_dict[session_id]

    # 基于内存的记忆存储
    _store_in_memory: dict[str, ChatMessageHistory] = {}

    def _get_history_in_memory(self, session_id: str) -> BaseChatMessageHistory:
        """默认的基于内存的记忆"""
        if session_id not in self._store_in_memory:
            self._store_in_memory[session_id] = ChatMessageHistory()
        return self._store_in_memory[session_id]