from datetime import datetime
from typing import List, Optional, Dict, Iterator
from uuid import uuid4
from enum import Enum

from ...io.rocksdict import IndexedRocksDB
from .L0_dialogue import Dialogue, Message, Thread, DialogueManager
from .L1_facts import Fact
from .L2_concept.models import Concept
from .L3_thematic_graph.models import ThematicGraph
from .L4_core_view.models import CoreView
from .models import ConversationCognitive, FinalCognitive
from .types import MemoryType
from .utils import generate_key

class MemoryManager:
    """记忆管理

    记忆管理包括：
    L0: 对话，Dialogue 应当被持久化
    L1: 事实，Fact 应当被持久化
    L2: 概念，Concept 应当被持久化
    L3: 主题，ThematicGraph 应当被持久化
    L4: 观点，CoreView 应当被持久化
    """
    def __init__(self, db: IndexedRocksDB):
        self.db = db
