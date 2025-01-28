from typing import Dict, List, Union, Any

import uuid
import logging

from ....io.rocksdict import IndexedRocksDB
from ..types import MemoryType
from ..utils import generate_key
from .models import Message, QA, Thread

class QAManager():
    """问答管理器，保存一个 thread_id 的所有问答"""
    def __init__(self, db: IndexedRocksDB, user_id: str = None, logger: logging.Logger = None):
        self.user_id = user_id or "default"
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
        data = self.db[generate_key(MemoryType.THREAD, self.user_id, thread_id)]
        if data:
            return Thread(**data)
        else:
            return None
    
    def last_thread(self):
        """获取最后一个对话"""
        threads = self.all_threads()
        return threads[-1] if threads else None

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

    def retrieve(self, thread_id: str, messages: List[Message] = None):
        """检索处理器
        1. 如果 messages 包含 system 角色就先将 system 角色消息置顶到 short_memory 中
        2. 提取所有 L0 级别的问答，追加到 short_memory 中
        3. 将 messages 中其他消息追加到 short_memory 中
        """
        messages = messages or []
        short_memory = []
        has_system_message = True if messages and messages[0].role == "system" else False

        if has_system_message:
            short_memory.append(messages[0])

        for qa in self.all_QAs(thread_id):
            if qa.level == "L0":
                short_memory.extend(qa.messages)
        
        if has_system_message:
            short_memory.extend(messages[1:])
        else:
            short_memory.extend(messages)
        
        return short_memory

