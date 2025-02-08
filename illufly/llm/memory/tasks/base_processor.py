from typing import List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel

from ....rocksdb import IndexedRocksDB
from .models import TaskStatus, ProcessingTask

class BaseProcessor:
    """处理器基类"""
    def __init__(
        self, 
        level: str,
        db: IndexedRocksDB,
        batch_size: int = 10,
        poll_interval: int = 60
    ):
        self.level = level
        self.db = db
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        
    async def scan_and_process(self):
        """扫描并处理任务"""
        while True:
            try:
                # 扫描待处理任务
                tasks = await self.get_pending_tasks()
                if len(tasks) >= self.batch_size:
                    await self.process_batch(tasks)
                    
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logging.error(f"{self.level} processor error: {e}")
                
    async def get_pending_tasks(self) -> List[ProcessingTask]:
        """获取待处理任务"""
        tasks = []
        prefix = f"task:{self.level}:"
        
        async for key, value in self.db.prefix_scan(prefix):
            task = ProcessingTask(**value)
            if task.status == TaskStatus.PENDING:
                tasks.append(task)
                if len(tasks) >= self.batch_size:
                    break
                    
        return tasks
        
    async def create_next_level_task(
        self,
        result: BaseModel,
        thread_id: str
    ):
        """创建下一层任务"""
        task = ProcessingTask(
            task_id=str(uuid4()),
            level=self.next_level,
            thread_id=thread_id,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            payload=result.model_dump()
        )
        
        key = f"task:{self.next_level}:{task.created_at.timestamp()}:{task.task_id}"
        await self.db.put(key, task.model_dump())