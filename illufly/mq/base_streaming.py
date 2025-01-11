import asyncio
import threading
import zmq.asyncio
import uuid
import logging
import time
import multiprocessing
import json
import os
import platform
import tempfile

from typing import Union, List, AsyncGenerator, Optional, AsyncIterator
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from enum import Enum
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field

from .message_bus import MessageBus
from .utils import get_ipc_path
from ..types import EventBlock
from .models import ServiceConfig, StreamingBlock
from .concurrency.base_runner import BaseRunner
from .concurrency.async_runner import AsyncRunner
from .concurrency.thread_runner import ThreadRunner
from .concurrency.process_runner import ProcessRunner

class ConcurrencyStrategy(Enum):
    ASYNC = "async"
    THREAD_POOL = "thread_pool"
    PROCESS_POOL = "process_pool"

class BaseStreamingService(ABC):
    """基础流式服务 - 统一服务端和客户端"""
    def __init__(self, config: ServiceConfig, logger=None):
        self.config = config
        self.logger = logger or logging.getLogger(config.service_name)
        self.runner: Optional[BaseRunner] = None
        self._running = False
        
    async def start(self):
        """启动服务"""
        if self._running:
            return
            
        if not self.runner:
            self.runner = self._create_runner()
        await self.runner.start()
        self._running = True
        
    async def stop(self):
        """停止服务"""
        if not self._running:
            return
            
        if self.runner:
            await self.runner.stop()
            self.runner = None
        self._running = False
            
    async def __call__(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        """客户端调用接口"""
        if not self._running:
            raise RuntimeError("Service not started")
        
        session_id = str(uuid.uuid4())
        
        # 订阅结果通道
        topic = f"llm.{self.config.service_name}.{session_id}"
        error_topic = f"{topic}.error"
        complete_topic = f"{topic}.complete"
        
        # 发送请求
        await self.runner.mq_server.send_json({
            "session_id": session_id,
            "prompt": prompt,
            "kwargs": kwargs
        })
        
        # 等待接收确认
        response = await self.runner.mq_server.recv_json()
        if response.get("status") != "accepted":
            raise RuntimeError(f"Request rejected: {response.get('error', 'Unknown error')}")
            
        # 接收结果流
        async for event in self.runner.message_bus.subscribe([topic, error_topic, complete_topic]):
            if "error" in event:
                raise RuntimeError(event["error"])
            elif event.get("status") == "complete":
                break
            else:
                yield StreamingBlock(**event)
            
    @abstractmethod
    async def process_request(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        """具体的请求处理逻辑（由子类实现）"""
        pass
        
    def _create_runner(self) -> BaseRunner:
        """创建对应的执行器"""
        if self.config.concurrency == ConcurrencyStrategy.ASYNC:
            return AsyncRunner(self.config, self)
        elif self.config.concurrency == ConcurrencyStrategy.THREAD_POOL:
            return ThreadRunner(self.config, self, self.config.max_workers)
        else:
            return ProcessRunner(self.config, self, self.config.max_workers) 