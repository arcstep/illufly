from typing import Callable, Optional
from langchain.memory import ConversationBufferMemory
from langchain.memory.chat_memory import BaseChatMemory
from langchain_core.messages import BaseMessage
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from typing import Any, Dict, Union, List
import copy

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
        if longterm_memory_factory is None:
            self.get_longterm_memory_factory = self._get_history_in_memory
        else:
            self.get_longterm_memory_factory = longterm_memory_factory

        # 使用窗口记忆、Token记忆等记忆体
        if shorterm_memory is None:
            self._shorterm_memory = ConversationBufferMemory()
        else:
            self._shorterm_memory = shorterm_memory

    # 返回短期记忆的消息列表
    def shorterm_messages(self, *args: Any, **kwargs: Any) -> List[BaseMessage]:
        memory = self.get_shorterm_memory(*args, **kwargs)
        return memory.buffer_as_messages

    # 返回长期记忆的消息列表
    def longterm_messages(self, *args: Any, **kwargs: Any) -> List[BaseMessage]:
        memory = self.get_shorterm_memory(*args, **kwargs)
        return memory.chat_memory.messages

    # 返回短期记忆的管理器对象
    def get_shorterm_memory(self, *args: Any, **kwargs: Any) -> BaseChatMemory:
        session_id: Union[str, Tuple] = None
        if len(args) == 1 and not kwargs:
            # 如果只有一个位置参数，按照原来的逻辑处理
            session_id = args[0]
            history = self.get_longterm_memory_factory(session_id)
        else:
            # 否则，将所有参数传递给 get_longterm_memory_factory
            history = self.get_longterm_memory_factory(*args, **kwargs)
            
            # 将 kwargs 转换为元组，以便用作字典的键
            session_id = tuple(kwargs.items())

        # 动态建立短期记忆
        if session_id is not None:
            if session_id not in self._shorterm_memory_store:
                self._shorterm_memory_store[session_id] = copy.copy(self._shorterm_memory)
                self._shorterm_memory_store[session_id].chat_memory = history
            return self._shorterm_memory_store[session_id]
        else:
            raise ValueError("Session ID is required")        

    def _get_history_in_memory(self, session_id: str) -> BaseChatMessageHistory:
        """默认的基于内存的记忆"""
        if session_id not in self._history_in_memory:
            self._history_in_memory[session_id] = ChatMessageHistory()
        return self._history_in_memory[session_id]