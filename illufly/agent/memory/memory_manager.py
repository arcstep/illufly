from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4
from enum import Enum

import logging

from ...rocksdb import IndexedRocksDB, default_rocksdb
from ...thread.models import HistoryMessage
from .types import MemoryType

MESSAGE_MODEL = "message"

class MemoryManager:
    """记忆管理

    记忆管理包括：
    L0: 对话，QA 应当被持久化
    L1: 事实，Fact 应当被持久化
    L2: 概念，Concept 应当被持久化
    L3: 主题，ThematicGraph 应当被持久化
    L4: 观点，CoreView 应当被持久化
    """

    def __init__(self, db: IndexedRocksDB, logger: logging.Logger = None):
        self._logger = logger or logging.getLogger(__name__)

        self.db = db or default_rocksdb
        self.db.register_model(MESSAGE_MODEL, HistoryMessage)
        self.db.register_index(MESSAGE_MODEL, HistoryMessage, "created_with_thread")

    def _load_recent_messages(self, user_id: str, thread_id: str) -> str:
        """加载最近的消息"""
        messages = []
        history_messages = sorted(
            self.db.values(
                prefix=HistoryMessage.get_thread_prefix(user_id, thread_id)
            ),
            key=lambda x: x.completed_at
        )
        for m in history_messages[-10:]:
            if m.role in ["user", "assistant", "tool"]:
                messages.append(m.to_message())
        self._logger.info(f"load_memory: {messages}")
        return "\n".join([str(m['role']) + ": " + str(m['content']) for m in messages])

    def load_memory(self, user_id: str, thread_id: str, messages: List[Dict[str, Any]]) -> str:
        """加载记忆"""
        return self._load_recent_messages(user_id, thread_id)

    def save_memory(self, user_id: str, thread_id: str, messages: List[Dict[str, Any]]):
        """保存记忆"""
        pass
