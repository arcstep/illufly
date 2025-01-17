from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from enum import Enum
from pydantic import BaseModel, Field
import time

class BlockType(str, Enum):
    START = "start"
    PROGRESS = "progress"
    CHUNK = "chunk"
    TOOLS_CALL_CHUNK = "tools_call_chunk"
    USAGE = "usage"
    END = "end"

class StreamingBlock(BaseModel):
    """流式处理块"""
    block_type: BlockType = Field(default=BlockType.CHUNK)
    content: str = Field(default="")
    topic: str = Field(default="")
    created_at: float = Field(default=time.time())
    thread_id: str = Field(default="")
    seq: int = Field(default=0)
