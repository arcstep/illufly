from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"      # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"         # 处理失败
    TIMEOUT = "timeout"       # 处理超时

class ProcessingTask(BaseModel):
    """处理任务"""
    task_id: str
    level: str  # fact, concept, theme, view
    thread_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    payload: Dict
    error: Optional[str] = None
    retry_count: int = 0
