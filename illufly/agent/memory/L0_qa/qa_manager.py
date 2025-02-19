from typing import Dict, List, Union, Any

import uuid
import logging

from .....rocksdb import IndexedRocksDB
from ..types import MemoryType, TaskState
from ..utils import generate_key
from .models import Message, QA

class QAManager():
    """问答管理器，保存一个 thread_id 的所有问答"""
    def __init__(self, db: IndexedRocksDB, user_id: str = None, logger: logging.Logger = None):
        self.user_id = user_id or "default"
        self.db = db

        self.db.register_model(MemoryType.QA, QA)
        self.db.register_index(MemoryType.QA, QA, "task_summarize")
        self.db.register_index(MemoryType.QA, QA, "task_extract_facts")

        self._logger = logger or logging.getLogger(__name__)

    def set_qa(self, qa: QA):
        """添加一个对话"""
        if self.user_id != qa.user_id:
            raise ValueError("对话的用户ID与管理器的用户ID不匹配")
        self.db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())

    def get_qa(self, thread_id: str, qa_id: str):
        """获取一个对话"""
        return self.db[generate_key(MemoryType.QA, self.user_id, thread_id, qa_id)]
    
    def get_all(self, thread_id: str, limit: int = None):
        """获取所有对话"""
        parent_key = QA.generate_parent_key(self.user_id, thread_id)
        values = self.db.values(prefix=parent_key, limit=limit)
        self._logger.info(f"获取问答对清单：{values}")
        return [QA(**value) for value in values]

    def retrieve(self, thread_id: str, messages: List[Message] = None, limit: int = 10):
        """检索处理器
        1. 如果 messages 包含 system 角色就先将 system 角色消息置顶到 short_memory 中
        2. 默认返回最近的10轮对话
        3. 优先返回摘要而不是原始对话
        4. 更多对话应当通过概念、事实等方式提取到系统提示语中
        """
        if thread_id == "once":
            return messages
        
        messages = messages or []
        short_memory = []
        has_system_message = True if messages and messages[0].role == "system" else False

        # 如果包含系统消息，则将系统消息置顶到 short_memory 中
        if has_system_message:
            short_memory.append(messages[0])

        # 返回最近的10轮对话
        for qa in self.get_all(thread_id)[:limit]:
            # 优先返回摘要
            short_memory.extend(qa.summary or qa.messages)
        
        if has_system_message:
            short_memory.extend(messages[1:])
        else:
            short_memory.extend(messages)
        
        return short_memory

