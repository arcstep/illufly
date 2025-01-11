from enum import Enum
from typing import Optional
from pydantic import BaseModel

class ConcurrencyStrategy(str, Enum):
    """并发策略"""
    ASYNC = "async"
    THREAD_POOL = "thread_pool"
    PROCESS_POOL = "process_pool"

class ServiceConfig(BaseModel):
    """服务配置"""
    service_name: str
    concurrency: ConcurrencyStrategy = ConcurrencyStrategy.ASYNC
    max_requests: int = 1000
    max_workers: Optional[int] = None
    mq_address: str = "tcp://127.0.0.1:5555"
    message_bus_address: str = "message_bus"

class StreamingBlock(BaseModel):
    """流式响应块"""
    block_type: str  # start, chunk, end, error
    content: Optional[str] = None
    error: Optional[str] = None 