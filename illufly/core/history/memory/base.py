from abc import ABC, abstractmethod
from typing import List, Union
import copy

class BaseMemoryHistory(ABC):
    def __init__(self, agent_class: str="CHAT_AGENT", agent_name: str="default"):
        self.memory = {}
        self.reset_init(agent_class, agent_name)

    def reset_init(self, agent_class: str, agent_name: str):
        self.agent_class = agent_class
        self.agent_name = agent_name

    def list_threads(self):
        """列举所有记忆线"""
        return sorted(self.memory.keys())

    @property
    def last_thread_id(self):
        all_thread_ids = self.list_threads()
        return all_thread_ids[-1] if all_thread_ids else None

    def save_memory(self, thread_id: str, memory: List[dict]):
        """根据 thread_id 保存记忆"""
        self.memory[thread_id] = copy.deepcopy(memory)

    def load_memory(self, thread_id: Union[str, int] = None):
        """
        加载记忆。

        如果 thread_id 是字符串，则直接加载指定线程的记忆；
        如果 thread_id 是整数，则将其当作索引，例如 thread_id=-1 表示加载最近一轮对话的记忆。
        """
        _thread_id = thread_id
        if isinstance(thread_id, str):
            return _thread_id, self.memory.get(thread_id, [])
        elif isinstance(thread_id, int):
            all_threads = self.list_threads()
            if all_threads:
                _thread_id = all_threads[thread_id]
                return _thread_id, self.memory.get(_thread_id, [])

        return _thread_id, []
