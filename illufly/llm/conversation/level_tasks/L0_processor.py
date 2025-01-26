from typing import List
from datetime import datetime, timedelta
from uuid import uuid4

from .base_processor import BaseProcessor
from ..L0_dialogue import Dialogue
from ..L1_facts import FactSummary, FactQueue

class DialogueProcessor(BaseProcessor):
    """对话处理器：L0 → L1"""
    def __init__(self, db: IndexedRocksDB, llm: ChatOpenAI):
        super().__init__("dialogue", db, batch_size=5)
        self.llm = llm
        self.next_level = "fact"
        
    async def process_batch(self, tasks: List[ProcessingTask]):
        """处理对话批次，提取事实"""
        for task in tasks:
            try:
                # 1. 获取对话数据
                dialogue = Dialogue(**task.payload)
                
                # 2. 提取事实
                facts = await self._extract_facts(dialogue)
                
                # 3. 获取或创建事实队列
                fact_queue = await self._get_or_create_fact_queue(dialogue.thread_id)
                
                # 4. 合并新事实
                for fact in facts:
                    fact_queue.add_fact(fact)
                
                # 5. 创建下一层任务
                await self.create_next_level_task(
                    fact_queue,
                    dialogue.thread_id
                )
                
                # 6. 更新任务状态
                await self._update_task_status(task.task_id, TaskStatus.COMPLETED)
                
            except Exception as e:
                await self._update_task_status(
                    task.task_id, 
                    TaskStatus.FAILED,
                    str(e)
                )
                
    async def _extract_facts(self, dialogue: Dialogue) -> List[FactSummary]:
        """从对话中提取事实"""
        prompt = f"""
        从以下对话中提取关键事实，每个事实不超过200字符。
        对话内容：
        用户：{dialogue.input_text}
        AI：{dialogue.output_text}
        
        请以JSON格式返回事实列表，每个事实包含：
        - title: 事实标题（30字以内）
        - content: 事实内容（200字以内）
        """
        
        response = await self.llm.chat_complete(prompt)
        facts_data = json.loads(response)
        
        return [
            FactSummary(
                thread_id=dialogue.thread_id,
                title=item["title"],
                content=item["content"],
                timestamp=dialogue.request_time,
                source_chat_threads=[dialogue.thread_id],
                window_start=dialogue.request_time,
                window_end=dialogue.request_time + timedelta(hours=1)
            )
            for item in facts_data
        ]
        
    async def _get_or_create_fact_queue(self, thread_id: str) -> FactQueue:
        """获取或创建事实队列"""
        key = f"fact_queue:{thread_id}"
        data = await self.db.get(key)
        if data:
            return FactQueue(**data)
        return FactQueue(thread_id=thread_id) 