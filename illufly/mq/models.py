from enum import Enum
from typing import Optional
from pydantic import BaseModel, model_validator

class ConcurrencyStrategy(str, Enum):
    """并发策略"""
    ASYNC = "async"
    THREAD_POOL = "thread_pool"
    PROCESS_POOL = "process_pool"

class ServiceConfig(BaseModel):
    """服务配置"""
    service_name: str = None
    concurrency: ConcurrencyStrategy = ConcurrencyStrategy.ASYNC
    max_requests: int = 1000
    max_workers: Optional[int] = None
    mq_address: Optional[str] = None
    message_bus_address: str = "message_bus"
    class_name: str = None

    @model_validator(mode='before')
    @classmethod
    def init_mq_service_and_address(cls, values):
        class_name = values.get("class_name")
        service_name = values.get("service_name") or class_name
        mq_address = values.get("mq_address")
        if not mq_address and class_name:
            mq_address = f"inproc://service.{class_name}"
        values["service_name"] = service_name
        values["mq_address"] = mq_address
        return values

class StreamingBlock(BaseModel):
    """流式响应块"""
    block_type: str  # start, chunk, end, error
    content: Optional[str] = None
    error: Optional[str] = None 
    process_id: Optional[str] = None
    thread_id: Optional[str] = None