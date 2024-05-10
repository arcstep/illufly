from typing import Callable, Optional
from langchain.memory import ConversationBufferMemory
from langchain.memory.chat_memory import BaseChatMemory
from langchain_core.messages import BaseMessage
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from typing import Any, Dict, Union, List
from copy import deepcopy

class MemoryManager:
    """实现记忆的工厂类，将短期记忆和持久化记忆绑定在一起管理。
    
    默认将记忆存储在内存中，但可以替换为redis存储等持久化方案；
    也支持按对话轮次、Token数、知识图谱等管理短期记忆。
    """

    # 短期记忆管理，用于记忆模板
    _shorterm_memory: BaseChatMemory
    
    # 为每一个session_id单独建立记忆管理器
    _shorterm_memory_store: dict[str, BaseChatMemory] = {}

    # 基于内存的记忆存储
    _history_in_memory: dict[str, ChatMessageHistory] = {}

    # 记忆存储的回调函数，要求使用 session_id 位置参数
    get_longterm_memory_factory: Callable[[str], BaseChatMessageHistory]

    def __init__(
        self,
        longterm_memory_factory: Optional[Callable[[str], BaseChatMessageHistory]] = None,
        shorterm_memory: Optional[BaseChatMemory] = None
    ) -> None:
        # 默认使用内存保存长期记忆
        # 可更换保存到redis、文件、数据库等
        if longterm_memory_factory is None:
            self.get_longterm_memory_factory = self._get_history_in_memory
        else:
            self.get_longterm_memory_factory = longterm_memory_factory

        # 默认使用内存保存窗口记忆
        # 可更换为使用限定对话窗口、限定总Token数等
        if shorterm_memory is None:
            self._shorterm_memory = ConversationBufferMemory()
        else:
            self._shorterm_memory = shorterm_memory

    # 返回短期记忆的消息列表
    def shorterm_messages(self, session_id: str = "default") -> List[BaseMessage]:
        memory = self.get_shorterm_memory(session_id)
        return memory.buffer_as_messages

    # 返回长期记忆的消息列表
    def longterm_messages(self, session_id: str = "default") -> List[BaseMessage]:
        memory = self.get_shorterm_memory(session_id)
        return memory.chat_memory.messages

    # 返回记忆管理器对象
    def get_shorterm_memory(self, session_id: str = "default") -> BaseChatMemory:
        if session_id not in self._shorterm_memory_store:
            history = self.get_longterm_memory_factory(session_id)
            self._shorterm_memory_store[session_id] = deepcopy(self._shorterm_memory)
            self._shorterm_memory_store[session_id].chat_memory = history

        return self._shorterm_memory_store[session_id]

    def _get_history_in_memory(self, session_id: str) -> BaseChatMessageHistory:
        """默认的基于内存的记忆"""
        if session_id not in self._history_in_memory:
            self._history_in_memory[session_id] = ChatMessageHistory()
        return self._history_in_memory[session_id]