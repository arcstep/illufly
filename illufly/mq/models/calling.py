from typing import List, Optional
from pydantic import BaseModel, Field

from .models import StreamingBlock
from .thread import StreamingThread
from .enum import BlockType

import time

class StreamingCalling(BaseModel):
    """
    调用上下文，包含多个计算线程
    每次调用可能发生多次大模型或工具的计算，而每次计算都可以是流式返回多个 StreamingBlock 块。
    """
    calling_id: str
    threads: List[StreamingThread] = []
    created_at: float = Field(default_factory=lambda: time.time())

    def add_thread(self, thread: StreamingThread) -> None:
        """添加一个新的计算线程"""
        if any(t.thread_id == thread.thread_id for t in self.threads):
            raise ValueError(f"Thread {thread.thread_id} already exists")
        self.threads.append(thread)

    def get_or_create_thread(self, thread_id: str) -> StreamingThread:
        """获取或创建一个计算线程"""
        for thread in self.threads:
            if thread.thread_id == thread_id:
                return thread
        new_thread = StreamingThread(thread_id=thread_id)
        self.add_thread(new_thread)
        return new_thread

    def add_block(self, block: StreamingBlock) -> None:
        """添加一个数据块到指定的线程中"""
        if not block.thread_id:
            raise ValueError("Block must have a thread_id")
        thread = self.get_or_create_thread(block.thread_id)
        thread.add_block(block)

    def get_thread(self, thread_id: str) -> Optional[StreamingThread]:
        """获取指定的计算线程"""
        for thread in self.threads:
            if thread.thread_id == thread_id:
                return thread
        return None

    def get_threads(self, completed_only: bool = False) -> List[StreamingThread]:
        """获取所有计算线程，可以只获取已完成的线程"""
        if completed_only:
            return [thread for thread in self.threads if thread.is_completed()]
        return self.threads

    def get_blocks(self, thread_id: str, block_type: Optional[BlockType] = None) -> List[StreamingBlock]:
        """获取指定线程的所有数据块，可以按类型过滤"""
        thread = self.get_thread(thread_id)
        if thread:
            return thread.get_blocks(block_type)
        return []

    def get_last_thread(self) -> Optional[StreamingThread]:
        """获取最后一个计算线程"""
        return self.threads[-1] if self.threads else None

    def is_completed(self) -> bool:
        """检查所有线程是否都已完成"""
        return all(thread.is_completed() for thread in self.threads)
