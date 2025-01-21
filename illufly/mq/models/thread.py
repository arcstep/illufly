from typing import List, Optional
from pydantic import BaseModel, Field

from .enum import BlockType
from .models import StreamingBlock

import time

class StreamingThread(BaseModel):
    """
    每个线程可以有多个 StreamingBlock 块，代表一次完整的计算过程
    """
    thread_id: str
    blocks: List[StreamingBlock] = []
    created_at: float = Field(default_factory=lambda: time.time())

    def add_block(self, block: StreamingBlock) -> None:
        """添加一个数据块到线程中"""
        if not block.thread_id:
            block.thread_id = self.thread_id
        elif block.thread_id != self.thread_id:
            raise ValueError(f"Block thread_id {block.thread_id} does not match thread {self.thread_id}")
        self.blocks.append(block)

    def get_blocks(self, block_type: Optional[BlockType] = None) -> List[StreamingBlock]:
        """获取线程中的所有数据块，可以按类型过滤"""
        if block_type is None:
            return self.blocks
        return [block for block in self.blocks if block.block_type == block_type]

    def get_last_block(self, block_type: Optional[BlockType] = None) -> Optional[StreamingBlock]:
        """获取最后一个数据块，可以按类型过滤"""
        blocks = self.get_blocks(block_type)
        return blocks[-1] if blocks else None

    def is_completed(self) -> bool:
        """检查线程是否已完成（存在 END 类型的块）"""
        return any(block.block_type == BlockType.END for block in self.blocks)
