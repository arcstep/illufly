from abc import ABC, abstractmethod
from typing import List

class BaseMemoryHistory(ABC):
    def __init__(self, agent_class: str="CHAT_AGENT", agent_name: str="default"):
        self.reset_init(agent_class, agent_name)

    def reset_init(self, agent_class: str, agent_name: str):
        self.agent_class = agent_class
        self.agent_name = agent_name

    @abstractmethod
    def list_threads(self):
        """列举所有记忆线"""
        pass

    @property
    def last_thread_id(self):
        all_thread_ids = self.list_threads()
        return all_thread_ids[-1] if all_thread_ids else None

    @abstractmethod
    def last_thread_id_count(self):
        """获取最近一轮对话的线程 ID"""
        pass

    @abstractmethod
    def save_memory(self, thread_id: str, memory: List[dict]):
        """根据 thread_id 保存记忆"""
        pass

    @abstractmethod
    def load_memory(self, thread_id: str):
        """根据 thread_id 加载记忆"""
        pass
