import asyncio
import zmq.asyncio
import logging

from typing import Union, List, Dict, Any, Optional, AsyncIterator, Iterator, Awaitable
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from enum import Enum
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from inspect import isasyncgenfunction, isgeneratorfunction, iscoroutinefunction

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

    if not prompt:
        raise ValueError("Prompt cannot be Empty")
    
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
                if event.get("error"):
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
    def __init__(self, service_config: ServiceConfig=None, service_name: str=None, logger=None):
        self.service_config = service_config or ServiceConfig(
            service_name=service_name,
            class_name=self.__class__.__name__
        )
        self._logger = logger or logging.getLogger(self.service_config.service_name)
        self.runner: Optional[BaseRunner] = None
        self._running = False
        
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """确保有可用的事件循环，如果需要则创建新的"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
        
    def start(self) -> None:
        """同步启动服务"""
        loop = self._ensure_loop()
        if loop.is_running():
            raise RuntimeError("Cannot call start() from an async context. Use start_async() instead.")
        loop.run_until_complete(self.start_async())
        
    async def start_async(self) -> None:
        """异步启动服务"""
        if self._running:
            return
            
        self._logger.info(f"Starting service on {self.service_config.mq_address}")
        self.runner = self._create_runner()
        self.runner.service = self
        await self.runner.start_async()  # 使用异步版本
        self._running = True
        
    def stop(self) -> None:
        """同步停止服务"""
        loop = self._ensure_loop()
        if loop.is_running():
            raise RuntimeError("Cannot call stop() from an async context. Use stop_async() instead.")
        loop.run_until_complete(self.stop_async())
        
    async def stop_async(self) -> None:
        """异步停止服务"""
        if not self._running:
            return
            
        self._logger.info("Stopping service")
        if self.runner:
            await self.runner.stop_async()  # 使用异步版本
        self._running = False
        
    def _is_async_context(self) -> bool:
        """检测是否在异步上下文中"""
        try:
            loop = asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False
            
    def __call__(self, prompt: str, **kwargs) -> Union[Iterator[StreamingBlock], AsyncIterator[StreamingBlock]]:
        """智能调用入口，根据上下文自动选择同步或异步方式"""
        if self._is_async_context():
            self._logger.debug("Detected async context, using async call")
            return self.call_async(prompt, **kwargs)
        else:
            self._logger.debug("Detected sync context, using sync call")
            return self.call(prompt, **kwargs)
    
    def call(self, prompt: str, **kwargs) -> Iterator[StreamingBlock]:
        """同步调用实现"""
        if not self._running:
            raise RuntimeError("Service not started")
            
        if not prompt:
            raise ValueError("Prompt cannot be Empty")
            
        self._logger.debug("Starting synchronous streaming request")
        loop = self._ensure_loop()
        
        async_iter = self.call_async(prompt, **kwargs)
        while True:
            try:
                block = loop.run_until_complete(async_iter.__anext__())
                yield block
            except StopAsyncIteration:
                break
            
    async def call_async(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        """异步调用接口"""
        if not self._running:
            raise RuntimeError("Service not started")
            
        if not prompt:
            raise ValueError("Prompt cannot be Empty")
            
        self._logger.debug("Starting async streaming request")
        async for block in request_streaming_response(
            context=self.runner.context,
            address=self.service_config.mq_address,
            service_name=self.service_config.service_name,
            prompt=prompt,
            logger=self._logger,
            **kwargs
        ):
            yield block

    @abstractmethod
    def process(self, prompt: str, **kwargs) -> Union[
        StreamingBlock,  # 同步返回值
        Iterator[StreamingBlock],  # 同步生成器
        AsyncIterator[StreamingBlock],  # 异步生成器
        Awaitable[StreamingBlock]  # 异步返回值
    ]:
        """服务端处理请求的抽象方法，支持多种实现方式"""
        raise NotImplementedError
        
    async def _adapt_process_request(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        """适配不同的 process 实现为统一的异步迭代器"""
        result = self.process(prompt, **kwargs)
        
        # 检查实现类型
        if isasyncgenfunction(self.process):
            # 异步生成器
            self._logger.debug("Using async generator implementation")
            async for block in result:
                yield block
                
        elif isgeneratorfunction(self.process):
            # 同步生成器
            self._logger.debug("Using sync generator implementation")
            for block in result:
                yield block
                
        elif iscoroutinefunction(self.process):
            # 异步返回值
            self._logger.debug("Using async return implementation")
            block = await result
            yield block
            
        else:
            # 同步返回值
            self._logger.debug("Using sync return implementation")
            yield result

    def _create_runner(self) -> BaseRunner:
        """创建对应的执行器"""
        if self.service_config.concurrency == ConcurrencyStrategy.ASYNC.value:
            return AsyncRunner(
                config=self.service_config,
                service=self,
                logger=self._logger
            )
        elif self.service_config.concurrency == ConcurrencyStrategy.THREAD_POOL.value:
            return ThreadRunner(
                config=self.service_config,
                service=self,
                max_workers=self.service_config.max_workers,
                logger=self._logger
            )
        elif self.service_config.concurrency == ConcurrencyStrategy.PROCESS_POOL.value:
            self._logger.warning("PROCESS_POOL: %s", self.service_config)
            return ProcessRunner(
                config=self.service_config,
                service=self,
                max_workers=self.service_config.max_workers,
                logger=self._logger
            ) 
        else:
            raise ValueError(f"Invalid concurrency strategy: {self.service_config.concurrency}")

    def __enter__(self) -> 'BaseStreamingService':
        """同步上下文管理器入口"""
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """同步上下文管理器退出"""
        self.stop()
        
    async def __aenter__(self) -> 'BaseStreamingService':
        """异步上下文管理器入口"""
        await self.start_async()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器退出"""
        await self.stop_async() 