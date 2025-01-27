from datetime import datetime
from typing import List, Optional, Dict, Iterator
from uuid import uuid4

from ...io.rocksdict import IndexedRocksDB
from .L0_dialogue.models import Dialogue, Message
from .L1_facts import Fact
from .models import ConversationCognitive, FinalCognitive, Concept

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
        # 注册模型和必要的索引
        self.db.register_model("dialogue", Dialogue)
        self.db.register_indexes("dialogue", Dialogue, "thread_id")
        self.db.register_indexes("dialogue", Dialogue, "request_time")
        
        self.db.register_model("concept", Concept)
        self.db.register_indexes("concept", Concept, "thread_id")
        
        # ... 其他模型的注册 ...
        
    def add_dialogue(self, dialogue: Dialogue) -> str:
        """添加新的对话记录"""
        # 保存对话记录
        self.db.update_with_indexes(
            "dialogue",
            dialogue.dialogue_id,
            dialogue.model_dump()
        )
        
        return dialogue.dialogue_id
        
    def get_dialogue(self, dialogue_id: str) -> Optional[Dialogue]:
        """获取单个对话记录"""
        data = self.db[dialogue_id]
        return Dialogue(**data) if data else None
        
    def get_thread_dialogues(
        self,
        thread_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Iterator[Dialogue]:
        """获取线程的对话列表"""
        for key in self.db.iter_keys_with_indexes(
            "dialogue", "thread_id", thread_id
        ):
            dialogue = self.db.get(key)
            if dialogue and self._in_time_range(dialogue, start_time, end_time):
                yield dialogue

    def get_conversation_cognitive(self, thread_id: str) -> ConversationCognitive:
        """按需构建认知状态"""
        # 查询相关的所有数据
        dialogues = list(self.get_thread_dialogues(thread_id))
        facts = list(self.get_thread_facts(thread_id))
        concepts = list(self.get_thread_concepts(thread_id))
        themes = list(self.get_thread_themes(thread_id))
        views = list(self.get_thread_views(thread_id))
        
        # 构建认知状态
        return ConversationCognitive(
            thread_id=thread_id,
            dialogues=dialogues,
            facts=facts,
            concepts=concepts,
            themes=themes,
            views=views
        )

    def get_thread_concepts(self, thread_id: str) -> Iterator[Concept]:
        """获取线程的概念列表"""
        for key in self.db.iter_keys_with_indexes(
            "concept", "thread_id", thread_id
        ):
            concept = self.db.get(key)
            if concept:
                yield concept

    def get_thread_facts(self, thread_id: str) -> Iterator[Fact]:
        """获取线程的事实列表"""
        for key in self.db.iter_keys_with_indexes(
            "facts", "thread_id", thread_id
        ):
            facts = self.db.get(key)
            if facts:
                yield facts

    def get_thread_themes(self, thread_id: str) -> Iterator[str]:
        """获取线程的主题列表"""
        for key in self.db.iter_keys_with_indexes(
            "themes", "thread_id", thread_id
        ):
            theme = self.db.get(key)
            if theme:
                yield theme

    def get_thread_views(self, thread_id: str) -> Iterator[str]:
        """获取线程的视图列表"""
        for key in self.db.iter_keys_with_indexes(
            "views", "thread_id", thread_id
        ):
            view = self.db.get(key)
            if view:
                yield view

    def get_conversation_cognitive(
        self, 
        user_id: str,
        thread_id: str
    ) -> Optional[ConversationCognitive]:
        """获取对话认知状态"""
        key = f"conversation:{user_id}:{thread_id}"
        data = self.db[key]
        return ConversationCognitive(**data) if data else None
        
    def update_conversation_cognitive(
        self,
        cognitive: ConversationCognitive
    ) -> None:
        """更新对话认知状态"""
        key = f"conversation:{cognitive.user_id}:{cognitive.thread_id}"
        self.db[key] = cognitive.model_dump()
        
    def get_final_cognitive(
        self,
        user_id: str
    ) -> Optional[FinalCognitive]:
        """获取用户最终认知状态"""
        key = f"final_cognitive:{user_id}"
        data = self.db[key]
        return FinalCognitive(**data) if data else None
        
    def update_final_cognitive(
        self,
        cognitive: FinalCognitive
    ) -> None:
        """更新用户最终认知状态"""
        key = f"final_cognitive:{cognitive.user_id}"
        self.db[key] = cognitive.model_dump()
        
    def create_thread(self, user_id: str) -> str:
        """创建新的对话线程"""
        return str(uuid4())  # 简单返回一个新的线程ID即可
        
    def list_user_threads(
        self,
        user_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[str]:
        """列出用户的所有对话线程"""
        # 通过认知状态查询
        threads = []
        prefix = f"cognitive:"
        for key, value in self.db.iter(prefix=prefix):
            cognitive = ConversationCognitive(**value)
            if cognitive.user_id == user_id:
                if start_time and end_time:
                    # 检查是否在时间范围内有对话
                    dialogues = self.get_thread_dialogues(
                        cognitive.thread_id,
                        start_time,
                        end_time
                    )
                    if dialogues:
                        threads.append(cognitive.thread_id)
                else:
                    threads.append(cognitive.thread_id)
        return threads

    def _in_time_range(self, dialogue: Dialogue, start_time: Optional[datetime], end_time: Optional[datetime]) -> bool:
        """检查对话是否在给定的时间范围内"""
        if start_time and dialogue['request_time'] < start_time:
            return False
        if end_time and dialogue['request_time'] > end_time:
            return False
        return True
