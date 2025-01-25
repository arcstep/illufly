from .base import BaseContext
from typing import Dict, Any, List
from datetime import datetime

class LongMemoryContext(BaseContext):
    """长期记忆上下文
    
    基于向量数据库存储长期对话记忆，支持语义搜索
    """
    def __init__(self, vector_db, max_memory_size=1000, **kwargs):
        super().__init__(**kwargs)
        self.vector_db = vector_db
        self.max_memory_size = max_memory_size

    def handle_input_messages(self, messages: List[Dict[str, Any]]):
        """根据当前对话内容检索相关记忆"""
        last_message = messages[-1]['content']
        # 从向量数据库检索相关记忆
        related_memories = self.vector_db.search(last_message, top_k=3)
        return related_memories + messages

    def handle_output_messages(self, messages: List[Dict[str, Any]]):
        """将重要对话存入长期记忆"""
        for message in messages:
            if self._is_important(message):
                self.vector_db.store({
                    'content': message['content'],
                    'timestamp': datetime.now(),
                    'metadata': {
                        'role': message['role'],
                        'importance': 1.0
                    }
                }) 