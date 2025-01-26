from datetime import datetime
from typing import List, Optional, Dict
from uuid import uuid4

from ...io.rocksdict import IndexedRocksDB
from .L0_dialogue.models import Dialogue, Message
from .models import ConversationCognitive, FinalCognitive

class ConversationManager:
    """连续对话管理"""
    def __init__(self, db: IndexedRocksDB):
        self.db = db
        # 注册模型和索引
        self.db.register_model("dialogue", Dialogue)
        self.db.register_indexes("dialogue", Dialogue, "thread_id")
        self.db.register_indexes("dialogue", Dialogue, "request_time")
        
    async def add_dialogue(self, dialogue: Dialogue) -> str:
        """添加新的对话记录"""
        # 生成对话ID
        dialogue_id = f"dialogue:{dialogue.thread_id}:{dialogue.request_time.timestamp()}"
        
        # 保存对话记录
        await self.db.update_with_indexes(
            "dialogue",
            dialogue_id,
            dialogue.model_dump()
        )
        
        return dialogue_id
        
    async def get_dialogue(self, dialogue_id: str) -> Optional[Dialogue]:
        """获取单个对话记录"""
        data = await self.db.get(dialogue_id)
        return Dialogue(**data) if data else None
        
    async def get_thread_dialogues(
        self, 
        thread_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dialogue]:
        """获取对话线程的所有对话记录"""
        # 使用时间范围查询
        if start_time and end_time:
            items = self.db.items_with_indexes(
                "dialogue",
                "request_time",
                start=start_time,
                end=end_time
            )
        else:
            # 使用thread_id查询
            items = self.db.items_with_indexes(
                "dialogue",
                "thread_id",
                thread_id
            )
            
        # 转换为对话对象并按时间排序
        dialogues = [
            Dialogue(**item[1])
            for item in items
            if Dialogue(**item[1]).thread_id == thread_id
        ]
        return sorted(dialogues, key=lambda x: x.request_time)
        
    async def get_conversation_cognitive(
        self, 
        thread_id: str
    ) -> Optional[ConversationCognitive]:
        """获取对话认知状态"""
        key = f"cognitive:{thread_id}"
        data = await self.db.get(key)
        return ConversationCognitive(**data) if data else None
        
    async def update_conversation_cognitive(
        self,
        cognitive: ConversationCognitive
    ) -> None:
        """更新对话认知状态"""
        key = f"cognitive:{cognitive.thread_id}"
        await self.db.put(key, cognitive.model_dump())
        
    async def get_final_cognitive(
        self,
        user_id: str
    ) -> Optional[FinalCognitive]:
        """获取用户最终认知状态"""
        key = f"final_cognitive:{user_id}"
        data = await self.db.get(key)
        return FinalCognitive(**data) if data else None
        
    async def update_final_cognitive(
        self,
        cognitive: FinalCognitive
    ) -> None:
        """更新用户最终认知状态"""
        key = f"final_cognitive:{cognitive.user_id}"
        await self.db.put(key, cognitive.model_dump())
        
    async def create_thread(self, user_id: str) -> str:
        """创建新的对话线程"""
        thread_id = str(uuid4())
        # 初始化认知状态
        cognitive = ConversationCognitive(
            user_id=user_id,
            thread_id=thread_id,
            dialogues=[],
            facts={},
            concepts=[],
            themes=[],
            views=[]
        )
        await self.update_conversation_cognitive(cognitive)
        return thread_id
        
    async def list_user_threads(
        self,
        user_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[str]:
        """列出用户的所有对话线程"""
        # 通过认知状态查询
        threads = []
        prefix = f"cognitive:"
        async for key, value in self.db.prefix_scan(prefix):
            cognitive = ConversationCognitive(**value)
            if cognitive.user_id == user_id:
                if start_time and end_time:
                    # 检查是否在时间范围内有对话
                    dialogues = await self.get_thread_dialogues(
                        cognitive.thread_id,
                        start_time,
                        end_time
                    )
                    if dialogues:
                        threads.append(cognitive.thread_id)
                else:
                    threads.append(cognitive.thread_id)
        return threads
