from datetime import datetime
from typing import Dict, List, Union, Any, Tuple
from pydantic import BaseModel, Field, computed_field

import uuid

from voidring import IndexedRocksDB
from ....thread.models import HistoryMessage
from ..types import TaskState

class QA(BaseModel):
    """L0: 一次问答
    """
    @classmethod
    def get_thread_prefix(cls, user_id: str, thread_id: str):
        return f"qa-{user_id}-{thread_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str, request_id: str):
        """用于 rocksdb 保存的 key"""
        return f"{cls.get_thread_prefix(user_id, thread_id)}-{request_id}"

    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="对话的请求ID")
    summary: Union[List[HistoryMessage], None] = Field(
        default=None,  # 先设置空列表作为默认值
        description="本轮对话摘要，一般是精简后的问答对消息"
    )
    task_summarize: TaskState = Field(default=TaskState.TODO, description="摘要任务执行状态")
    task_extract_facts: TaskState = Field(default=TaskState.TODO, description="事实提取任务执行状态")

    def task_summarize_completed(self):
        """摘要任务完成"""
        self.task_summarize = TaskState.COMPLETED

    def task_extract_facts_completed(self):
        """事实提取任务完成"""
        self.task_extract_facts = TaskState.COMPLETED
