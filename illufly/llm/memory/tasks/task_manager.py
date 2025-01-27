from typing import Dict
from datetime import datetime

from ....io.rocksdict import IndexedRocksDB
from .models import TaskStatus, ProcessingTask

class TaskManager:
    """任务管理器"""
    def __init__(self, db: IndexedRocksDB):
        self.db = db
        
    async def get_thread_progress(self, thread_id: str) -> Dict:
        """获取线程处理进度"""
        progress = {}
        for level in ["fact", "concept", "theme", "view"]:
            tasks = await self.get_thread_tasks(thread_id, level)
            progress[level] = {
                "total": len(tasks),
                "pending": sum(1 for t in tasks if t.status == TaskStatus.PENDING),
                "completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
                "failed": sum(1 for t in tasks if t.status == TaskStatus.FAILED)
            }
        return progress
        
    async def retry_failed_tasks(self, level: str = None):
        """重试失败任务"""
        prefix = f"task:{level}:" if level else "task:"
        
        async for key, value in self.db.prefix_scan(prefix):
            task = ProcessingTask(**value)
            if task.status == TaskStatus.FAILED and task.retry_count < 3:
                task.status = TaskStatus.PENDING
                task.retry_count += 1
                task.updated_at = datetime.now()
                await self.db.put(key, task.model_dump())