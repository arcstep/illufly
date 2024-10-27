import os
import json
import copy

from typing import Union, List

from .base import BaseHistory

class InMemoryHistory(BaseHistory):
    """基于内存的记忆管理"""

    def __init__(self, memory: dict = {}, **kwargs):
        super().__init__(**kwargs)
        self.memory = memory or {}

    def last_thread_id_count(self):
        all_thread_ids = self.list_threads()
        if all_thread_ids:
            ids = all_thread_ids[-1].split("-")
            return int(ids[-1]) + 1
        else:
            return 0

    # 列举所有记忆线
    def list_threads(self):
        return sorted(self.memory.keys())

    def save_memory(self, thread_id: str, memory: List[dict]):
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
