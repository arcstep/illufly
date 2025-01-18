import os
import logging
import json
import time
import uuid
import asyncio
import threading
from abc import ABC, abstractmethod

from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator

from ..async_utils import AsyncUtils
from ..mq.message_bus import MessageBus, StreamingBlock, BlockType
from .base_call import BaseCall

class BaseService(BaseCall):
    """请求之后从 MessageBus 做出回应
    
    支持同步和异步调用：
    1. call(): 同步调用，返回可迭代的响应
    2. async_call(): 异步调用，返回可异步迭代的响应
    
    使用示例:
    ```python
    class MyService(BaseService):
        def __init__(self, service_name: str = "test_service", message_bus_address: str = None):
            super().__init__(service_name, message_bus_address)
            self.register_method("server", async_handle=self._async_handler)
        
        async def _async_handler(self, message: str, thread_id: str, message_bus: MessageBus):
            response = {"block_type": "chunk", "content": f"收到消息: {message}"}
            message_bus.publish(thread_id, response)
            return response
    
    # 同步调用
    service = MyService()
    response = service.call(message="my_arg")
    for msg in response:
        print(msg)
        
    # 异步调用
    async for msg in await service.async_call(message="my_arg"):
        print(msg)
    ```
    """

    def __init__(self, service_name: str=None, message_bus_address: str = None, **kwargs):
        """初始化服务
        
        Args:
            service_name: 服务名称
            message_bus_address: MessageBus，如果为None则创建新的
        """
        super().__init__(**kwargs)
        self._service_name = service_name or f"{self.__class__.__name__}.{self.__hash__()}"
        self._message_bus_address = message_bus_address
        self._message_bus = MessageBus(
            address=message_bus_address,
            logger=self._logger
        )
        self._async_utils = AsyncUtils(logger=self._logger)
        self._processing_events = {}  # 用于跟踪每个调用的处理状态

    def __del__(self):
        """析构函数，确保资源被清理"""
        self.cleanup()

    def __call__(self, *args, **kwargs):
        return self.call(*args, **kwargs)

    def _get_thread_id(self):
        return f"{self._service_name}.{uuid.uuid1()}"

    def cleanup(self):
        """清理资源"""
        self._message_bus.cleanup()

    async def _process_and_end(self, *args, thread_id: str, **kwargs):
        """将处理和结束标记合并为一个顺序任务"""
        self._logger.info(f"Starting _process_and_end for thread: {thread_id}")
        try:
            await self.async_method(
                "server",
                *args,
                thread_id=thread_id,
                message_bus=self._message_bus,
                **kwargs
            )
        except Exception as e:
            self._logger.error(f"Processing resulted in error state: {e}")
            self._message_bus.publish(
                thread_id,
                StreamingBlock.create_error(
                    error=str(e),
                    topic=thread_id
                )
            )
        finally:
            self._message_bus.publish(
                thread_id,
                StreamingBlock.create_end(thread_id)
            )
            self._logger.info(f"Send <<END>> flag for thread: {thread_id}")

    def call(self, *args, **kwargs):
        """同步调用服务方法"""
        thread_id = self._get_thread_id()
        client_bus = MessageBus(
            address=self._message_bus_address,
            logger=self._logger
        )
        
        try:
            # 1. 先订阅并创建收集器
            client_bus.subscribe(thread_id)
            collector = client_bus.collect(timeout=30.0)
            
            # 2. 创建单个顺序任务
            with self._async_utils.managed_sync() as loop:
                task = loop.create_task(
                    self._process_and_end(
                        *args,
                        thread_id=thread_id,
                        **kwargs
                    )
                )                
                return self.Response(collector, [task], self._async_utils, self._logger)
                
        except Exception as e:
            self._logger.error(f"Error in sync call: {e}")
            client_bus.cleanup()
            raise

    async def async_call(self, *args, **kwargs):
        """异步调用服务方法"""
        thread_id = self._get_thread_id()
        client_bus = MessageBus(
            address=self._message_bus_address,
            logger=self._logger
        )
        
        try:
            # 1. 先订阅并创建收集器
            client_bus.subscribe(thread_id)
            collector = client_bus.async_collect(timeout=30.0)
            
            # 2. 创建单个顺序任务
            task = asyncio.create_task(
                self._process_and_end(
                    *args,
                    thread_id=thread_id,
                    **kwargs
                )
            )            
            return self.AsyncResponse(collector, [task], self._logger)
            
        except Exception as e:
            self._logger.error(f"Error in async call: {e}")
            client_bus.cleanup()
            raise

    class Response:
        def __init__(self, collector, tasks, async_utils, logger):
            self._collector = collector
            self._tasks = tasks
            self._async_utils = async_utils
            self._logger = logger
            self._is_closed = False
            self._cache_result = []

        def __iter__(self):
            if self._is_closed:
                for msg in self._cache_result:
                    yield msg         
                return
            try:
                for msg in self._collector:
                    self._cache_result.append(msg)
                    yield msg
                    if msg.block_type == BlockType.END:
                        break  # 收到结束标记后立即退出
                        
            except Exception as e:
                self._logger.error(f"Error during collection: {e}")
                raise
                
            finally:
                self._cleanup()

        def _cleanup(self):
            """清理资源"""
            if self._is_closed:
                return
                
            self._is_closed = True
            
            # 清理所有任务
            with self._async_utils.managed_sync() as loop:
                for task in self._tasks:
                    if not task.done():
                        task.cancel()
                        try:
                            loop.run_until_complete(task)
                        except asyncio.CancelledError:
                            pass
                        except Exception as e:
                            self._logger.error(f"Error cleaning up task: {e}")

    class AsyncResponse:
        def __init__(self, collector, tasks, logger):
            self._collector = collector
            self._tasks = tasks
            self._logger = logger
            self._is_closed = False
            self._cache_result = []

        async def __aiter__(self):
            if self._is_closed:
                for msg in self._cache_result:
                    yield msg
                return
            
            try:
                async for msg in self._collector:
                    self._cache_result.append(msg)
                    yield msg
                    if msg.block_type == BlockType.END:
                        break
                        
            except Exception as e:
                self._logger.error(f"Error during async collection: {e}")
                raise
                
            finally:
                await self._cleanup()

        async def _cleanup(self):
            """清理资源"""
            if self._is_closed:
                return
                
            self._is_closed = True
            
            # 清理任务
            for task in self._tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        self._logger.error(f"Error cleaning up task: {e}")
            
            # 关闭收集器
            try:
                await self._collector.aclose()
            except Exception as e:
                self._logger.error(f"Error closing collector: {e}")
    