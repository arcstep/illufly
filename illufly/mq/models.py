from enum import Enum
from typing import Optional
from pydantic import BaseModel, model_validator

import uuid
from .utils import get_ipc_path

class ServiceConfig(BaseModel):
    """服务配置"""
    service_name: str = None
    max_requests: int = 1000
    rep_address: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def init_mq_service_and_address(cls, values):
        """初始化服务配置"""
        prefix = "service"
        mid = values.get("service_name", "default")
        suffix = uuid.uuid4()
        default_values = {
            "rep_address": f"inproc://{prefix}-{mid}",
        }
        return {**default_values, **values}

class StreamingBlock(BaseModel):
    """流式响应块"""
    block_type: str = "chunk"  # start, chunk, end, error
    content: Optional[str] = None
    error: Optional[str] = None
