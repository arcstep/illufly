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

from typing import Union, List, Dict, Any, Optional, AsyncIterator
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

logger = logging.getLogger(__name__)

async def request_streaming_response(
    context: zmq.asyncio.Context,
    address: str,
    service_name: str,
    prompt: str,
    logger: Optional[logging.Logger] = None,
    timeout: float = 30.0,
    **kwargs
) -> AsyncIterator[StreamingBlock]:
    """发送请求并获取流式响应"""
    message_bus = MessageBus.instance()
    _logger = logger or logging.getLogger(__name__)
    client = context.socket(zmq.REQ)
    client.connect(address)
    
    try:
        # 第一阶段：初始化会话
        _logger.debug("Initializing session")
        await client.send_json({"command": "init"})
        init_response = await client.recv_json()
        
        if init_response["status"] != "success":
            raise RuntimeError(init_response.get("error", "Failed to initialize session"))
            
        session_id = init_response["session_id"]
        topic = init_response["topic"]
        
        # 创建订阅
        _logger.debug(f"Creating subscription for topic: {topic}")
        subscription = message_bus.subscribe([
            topic,
            f"{topic}.complete",
            f"{topic}.error"
        ])
        
        # 第二阶段：发送实际请求
        request = {
            "command": "process",
            "session_id": session_id,
            "prompt": prompt,
            "kwargs": kwargs
        }
        _logger.debug(f"Sending process request: {request}")
        await client.send_json(request)
        
        # 接收流式响应
        async with asyncio.timeout(timeout):
            async for event in subscription:
                _logger.debug(f"Received event: {event}")
                if "error" in event:
                    raise RuntimeError(event["error"])
                elif event.get("status") == "complete":
                    _logger.debug("Received completion notice")
                    break
                else:
                    yield StreamingBlock(**event)
        
        # 等待最终处理结果
        _logger.debug("Waiting for final response")
        response = await client.recv_json()
        if response["status"] != "success":
            raise RuntimeError(response.get("error", "Request failed"))
            
    except asyncio.TimeoutError:
        raise RuntimeError(f"Request timed out after {timeout} seconds")
        
    finally:
        _logger.debug("Closing client connection")
        client.close(linger=0)

class BaseStreamingService(ABC):
    """基础流式服务 - 统一服务端和客户端"""
    def __init__(self, config: ServiceConfig, logger: logging.Logger = None):
        self.config = config
        self._logger = logger or logging.getLogger(__name__)
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
        
        async for block in request_streaming_response(
            context=self.runner.context,
            address=self.config.mq_address,
            service_name=self.config.service_name,
            prompt=prompt,
            message_bus=self.runner.message_bus,
            **kwargs
        ):
            yield block
        
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