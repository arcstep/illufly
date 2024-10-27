from abc import ABC, abstractmethod
from typing import List
import time
import random

class ThreadIDGenerator:
    def __init__(self, counter: int=0):
        self.counter = counter

    def create_id(self, last_count: str=None):
        if last_count:
            self.counter = int(last_count)
        while True:
            timestamp = str(int(time.time()))[-6:]
            random_number = f'{random.randint(0, 9999):04}'
            counter_str = f'{self.counter:04}'
            yield f'{timestamp}-{random_number}-{counter_str}'
            self.counter = 0 if self.counter == 9999 else self.counter + 1

thread_id_gen = ThreadIDGenerator()


class BaseHistory(ABC):
    def __init__(self, agent_class: str="CHAT_AGENT", agent_name: str="default"):
        self.reset_init(agent_class, agent_name)

    def reset_init(self, agent_class: str, agent_name: str):
        self.agent_class = agent_class
        self.agent_name = agent_name

    @abstractmethod
    def list_threads(self):
        """列举所有记忆线"""
        pass

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
