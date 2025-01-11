from enum import Enum
from typing import Dict, Optional, Any, Union, List
from pydantic import BaseModel, Field
import time

class ServiceMode(str, Enum):
    """服务模式"""
    REQUEST_REPLY = 'req_rep'    # 请求响应模式
    PUSH_PULL = 'push_pull'      # 推拉模式
    PUB_SUB = 'pub_sub'         # 发布订阅模式
    ROUTER = 'router'           # 路由模式
    PIPELINE = 'pipeline'       # 管道模式

class ServiceStatus(str, Enum):
    """服务状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"

class ServiceRequest(BaseModel):
    """服务请求"""
    method: str
    params: Dict[str, Any] = {}

class ServiceResponse(BaseModel):
    """服务响应"""
    status: str
    message: Optional[str] = None
    data: Optional[Any] = None
    stream_id: Optional[str] = None

class ServiceInfo(BaseModel):
    """服务信息模型"""
    name: str
    methods: Dict[str, str]
    address: str
    status: ServiceStatus = ServiceStatus.ACTIVE
    service_mode: ServiceMode = ServiceMode.REQUEST_REPLY
    stream_address: Optional[str] = None
    last_heartbeat: float = Field(default_factory=time.time)

class RegistryRequest(BaseModel):
    """注册请求模型"""
    action: str
    service: str
    methods: Optional[Dict[str, str]] = None
    address: Optional[str] = None
    service_mode: ServiceMode = ServiceMode.REQUEST_REPLY
    stream_address: Optional[str] = None

class RegistryResponse(BaseModel):
    """注册响应模型"""
    status: str
    message: str
    data: Optional[Union[Dict, List[Dict]]] = None  # 允许字典或字典列表

class ConcurrencyMode(str, Enum):
    """并发模式"""
    ASYNC = 'async'          # 纯异步模式
    THREAD = 'thread'        # 单独线程模式
    THREADPOOL = 'threadpool'  # 线程池模式
