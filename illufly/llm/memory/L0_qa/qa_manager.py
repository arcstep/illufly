from typing import Dict, List, Union, Any

import uuid
import logging

from ....io.rocksdict import IndexedRocksDB
from ..types import MemoryType
from ..utils import generate_key
from .models import QA, Thread

class QAManager():
    """问答管理器，保存一个 thread_id 的所有问答"""
    def __init__(self, db: IndexedRocksDB, user_id: str = "default", logger: logging.Logger = None):
        self.user_id = user_id
        self.db = db
        self.QAs: Dict[str, List[QA]] = {}

        self.db.register_model(MemoryType.THREAD, Thread)

        self.db.register_model(MemoryType.QA, QA)
        self.db.register_indexes(MemoryType.QA, QA, "request_time")

        self._logger = logger or logging.getLogger(__name__)

    def create_thread(self, title: str = "", description: str = "", thread_id: str = None):
        """创建一个对话"""
        thread = Thread(user_id=self.user_id, title=title, description=description, thread_id=thread_id)
        self.db[thread.key] = thread.model_dump()
        return thread
    
    def get_thread(self, thread_id: str):
        """获取一个对话"""
        return self.db[generate_key(MemoryType.THREAD, self.user_id, thread_id)]
    
    def all_threads(self):
        """获取所有对话"""
        prefix_key = generate_key(MemoryType.THREAD, self.user_id)
        values = self.db.values(prefix=prefix_key)
        return [Thread(**value) for value in values]

    def add_QA(self, qa: QA):
        """添加一个对话"""
        if self.user_id != qa.user_id:
            raise ValueError("对话的用户ID与管理器的用户ID不匹配")
        self.db[qa.key] = qa.model_dump()

    def get_QA(self, thread_id: str, qa_id: str):
        """获取一个对话"""
        return self.db[generate_key(MemoryType.QA, self.user_id, thread_id, qa_id)]
    
    def all_QAs(self, thread_id: str):
        """获取所有对话"""
        parent_key = QA.generate_parent_key(self.user_id, thread_id)
        values = self.db.values(prefix=parent_key)
        self._logger.info(f"获取问答对清单：{values}")
        return [QA(**value) for value in values]

    def retrieve(self, thread_id: str):
        """检索处理器"""

        short_memory = []
        for dia in self.all_QAs(thread_id):
            if dia.level == "L0":
                short_memory.extend(dia.qa_message)
        return short_memory

