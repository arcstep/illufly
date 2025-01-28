from typing import List
from datetime import datetime, timedelta
from uuid import uuid4

from ..tasks import BaseProcessor
from ..L0_QA import QA
from ..L1_facts import Fact

class DialogueProcessor(BaseProcessor):
    """对话处理器：L0 → L1"""
    def __init__(self, db: IndexedRocksDB, llm: ChatOpenAI):
        super().__init__("QA", db, batch_size=5)
        self.llm = llm
        self.next_level = "fact"
        
    async def process_batch(self, tasks: List[ProcessingTask]):
        """处理对话批次，提取事实"""
        for task in tasks:
            try:
                # 1. 获取对话数据
                QA = QA(**task.payload)
                
                # 2. 提取事实
                facts = await self._extract_facts(QA)
                
                # 3. 获取或创建事实队列
                
                # 4. 合并新事实
                
                # 5. 创建下一层任务
                await self.create_next_level_task(
                    fact_queue,
                    QA.thread_id
                )
                
                # 6. 更新任务状态
                await self._update_task_status(task.task_id, TaskStatus.COMPLETED)
                
            except Exception as e:
                await self._update_task_status(
                    task.task_id, 
                    TaskStatus.FAILED,
                    str(e)
                )
                
    async def _extract_facts(self, QA: QA) -> List[Fact]:
        """从对话中提取事实"""
        prompt = f"""
        从以下对话中提取关键事实，每个事实不超过200字符。
        对话内容：
        用户：{QA.input_text}
        AI：{QA.output_text}
        
        请以JSON格式返回事实列表，每个事实包含：
        - title: 事实标题（30字以内）
        - content: 事实内容（200字以内）
        """
        
        response = await self.llm.chat_complete(prompt)
        facts_data = json.loads(response)
        
        return [
            Fact(
                thread_id=QA.thread_id,
                title=item["title"],
                content=item["content"],
                timestamp=QA.request_time,
                source_chat_threads=[QA.thread_id],
                window_start=QA.request_time,
                window_end=QA.request_time + timedelta(hours=1)
            )
            for item in facts_data
        ]
        