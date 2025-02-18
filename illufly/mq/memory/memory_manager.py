from datetime import datetime
from typing import List, Optional, Dict, Iterator
from uuid import uuid4
from enum import Enum

from .L0_qa import QA, SimpleMessage
from .L1_facts import Fact
from .L2_concept.models import Concept
from .L3_thematic_graph.models import ThematicGraph
from .L4_core_view.models import CoreView
from .types import MemoryType
from .utils import generate_key

class MemoryManager:
    """记忆管理

    记忆管理包括：
    L0: 对话，QA 应当被持久化
    L1: 事实，Fact 应当被持久化
    L2: 概念，Concept 应当被持久化
    L3: 主题，ThematicGraph 应当被持久化
    L4: 观点，CoreView 应当被持久化
    """

    def load_memory(self, user_id: str, thread_id: str, messages: List[SimpleMessage]):
        """加载记忆"""
        return []
