from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4
from enum import Enum

from ...thread.models import HistoryMessage
from .types import MemoryType

class MemoryManager:
    """记忆管理

    记忆管理包括：
    L0: 对话，QA 应当被持久化
    L1: 事实，Fact 应当被持久化
    L2: 概念，Concept 应当被持久化
    L3: 主题，ThematicGraph 应当被持久化
    L4: 观点，CoreView 应当被持久化
    """

    def load_memory(self, user_id: str, thread_id: str, messages: List[Dict[str, Any]]):
        """加载记忆"""
        return []
