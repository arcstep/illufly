from typing import Callable, Optional
from langchain.memory import ConversationBufferMemory
from langchain.memory.chat_memory import BaseChatMemory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

class MemoryManager:
    """实现记忆存储和提取"""

    # 短期记忆管理
    _shorterm_memory: BaseChatMemory

    # 记忆存储的回调函数，要求使用 session_id 位置参数
    get_longterm_memory_factory: Callable[[str], BaseChatMessageHistory]

    def __init__(
        self,
        longterm_memory_factory: Optional[Callable[[str], BaseChatMessageHistory]] = None,
        shorterm_memory: Optional[BaseChatMemory] = None
    ) -> None:
        if longterm_memory_factory is None:
            self.get_longterm_memory_factory = self._get_history_in_memory
        else:
            self.get_longterm_memory_factory = longterm_memory_factory

        # 使用窗口记忆、Token记忆等记忆体
        if shorterm_memory is None:
            self._shorterm_memory = ConversationBufferMemory()
        else:
            self._shorterm_memory = shorterm_memory

    # 根据 session_id 提取短期记忆
    def get_shorterm_memory(self, *args, **kwargs):
        if len(args) == 1 and not kwargs:
            # 如果只有一个位置参数，按照原来的逻辑处理
            session_id = args[0]
            history = self.get_longterm_memory_factory(session_id)
        else:
            # 否则，将所有参数传递给 get_longterm_memory_factory
            history = self.get_longterm_memory_factory(*args, **kwargs)

        # 关联 BaseChatMemory子类 和 BaseChatMessageHistory子类
        if isinstance(self._shorterm_memory.chat_memory, BaseChatMessageHistory):
            self._shorterm_memory.chat_memory = history

        return self._shorterm_memory

    # 基于内存的记忆存储
    _history_in_memory: dict[str, ChatMessageHistory] = {}

    def _get_history_in_memory(self, session_id: str) -> BaseChatMessageHistory:
        """默认的基于内存的记忆"""
        if session_id not in self._history_in_memory:
            self._history_in_memory[session_id] = ChatMessageHistory()
        return self._history_in_memory[session_id]