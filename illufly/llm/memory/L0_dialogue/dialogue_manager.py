from typing import Dict, List

import uuid

from ....io.rocksdict import IndexedRocksDB
from ..types import MemoryType
from ..utils import generate_key
from .models import Dialogue, Thread

class DialogueManager():
    """对话管理器，保存一个 thread_id 的所有对话"""
    def __init__(self, db: IndexedRocksDB, user_id: str = "default"):
        self.user_id = user_id
        self.db = db
        self.dialogues: Dict[str, List[Dialogue]] = {}

        self.db.register_model(MemoryType.THREAD, Thread)

        self.db.register_model(MemoryType.DIALOGUE, Dialogue)
        self.db.register_indexes(MemoryType.DIALOGUE, Dialogue, "request_time")

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

    def add_dialogue(self, dialogue: Dialogue):
        """添加一个对话"""
        if self.user_id != dialogue.user_id:
            raise ValueError("对话的用户ID与管理器的用户ID不匹配")
        self.db[dialogue.key] = dialogue.model_dump()

    def get_dialogue(self, thread_id: str, dialogue_id: str):
        """获取一个对话"""
        return self.db[generate_key(MemoryType.DIALOGUE, self.user_id, thread_id, dialogue_id)]
    
    def all_dialogues(self, thread_id: str):
        """获取所有对话"""
        prefix_key = generate_key(MemoryType.DIALOGUE, self.user_id, thread_id)
        values = self.db.values(prefix=prefix_key)
        return [Dialogue(**value) for value in values]
