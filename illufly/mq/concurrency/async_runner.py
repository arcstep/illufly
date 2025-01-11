from typing import AsyncIterator
import asyncio
import zmq.asyncio

from .base_runner import BaseRunner
from ..models import ServiceConfig, StreamingBlock

class AsyncRunner(BaseRunner):
    """异步执行器 - 直接在当前事件循环中处理请求"""
    # 异步执行器不需要额外的设置，直接使用基类的实现即可 
    pass
