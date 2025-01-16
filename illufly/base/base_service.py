import os
import logging
import json
import time
import uuid
import asyncio
import threading
from abc import ABC, abstractmethod

from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator

from ..mq.message_bus import MessageBus
from .base_call import BaseCall
from .async_service import AsyncService

class BaseService(BaseCall):
    """请求之后从 MessageBus 做出回应
    
    支持同步和异步调用：
    1. call(): 同步调用，返回可迭代的响应
    2. async_call(): 异步调用，返回可异步迭代的响应
    
    使用示例:
    ```python
    class MyService(BaseService):
        async def _async_handler(self, message: str, thread_id: str, message_bus: MessageBus):
            resp = {"status": "success", "message": f"收到消息: {message}"}
            message_bus.publish(thread_id, resp)
            message_bus.publish(thread_id, end=True)
            return resp
    
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
                
    def __init__(self, service_name: str, message_bus_address: str = None):
        """初始化服务
        
        Args:
            service_name: 服务名称
            message_bus_address: MessageBus，如果为None则创建新的
        """
        super().__init__()
        self._service_name = service_name
        self._message_bus_address = message_bus_address
        self._message_bus = MessageBus(
            address=message_bus_address,
            logger=self._logger
        )
        self._async_service = AsyncService(logger=self._logger)
        self._processing_events = {}  # 用于跟踪每个调用的处理状态

    def __del__(self):
        """析构函数，确保资源被清理"""
        self._message_bus.cleanup()

    def __call__(self, *args, **kwargs):
        return self.call(*args, **kwargs)

    def _get_thread_id(self):
        return f"{self._service_name}.{uuid.uuid1()}"

    def call(self, **kwargs):
        """同步调用服务方法"""
        thread_id = self._get_thread_id()
        client_bus = MessageBus(
            address=self._message_bus_address,
            logger=self._logger
        )
        
        try:
            # 1. 先订阅并创建收集器
            client_bus.subscribe(thread_id)
            collector = client_bus.collect(timeout=30.0)  # 添加超时保护
            
            # 2. 在后台执行服务方法
            with self._async_service.managed_sync() as loop:
                task = loop.create_task(
                    self.async_method(
                        "server",
                        thread_id=thread_id,
                        message_bus=self._message_bus,
                        **kwargs
                    )
                )
                
                # 3. 发送结束标记的任务
                end_task = loop.create_task(
                    self._send_end_block(thread_id)
                )
                
                return self.Response(collector, [task, end_task], self._async_service, self._logger)
                
        except Exception as e:
            self._logger.error(f"Error in sync call: {e}")
            client_bus.cleanup()
            raise

    async def async_call(self, **kwargs):
        """异步调用服务方法"""
        thread_id = self._get_thread_id()
        client_bus = MessageBus(
            address=self._message_bus_address,
            logger=self._logger
        )
        
        try:
            # 1. 先订阅并创建收集器
            client_bus.subscribe(thread_id)
            collector = client_bus.async_collect(timeout=30.0)  # 添加超时保护
            
            # 2. 在后台执行服务方法
            task = asyncio.create_task(
                self.async_method(
                    "server",
                    thread_id=thread_id,
                    message_bus=self._message_bus,
                    **kwargs
                )
            )
            
            # 3. 发送结束标记的任务
            end_task = asyncio.create_task(
                self._send_end_block(thread_id)
            )
            
            return self.AsyncResponse(collector, [task, end_task], self._logger)
            
        except Exception as e:
            self._logger.error(f"Error in async call: {e}")
            client_bus.cleanup()
            raise

    async def _send_end_block(self, thread_id: str):
        """等待处理完成后发送结束标记"""
        try:
            # 等待处理完成事件
            if thread_id in self._processing_events:
                await self._processing_events[thread_id].wait()
            
            # 发送结束标记
            self._message_bus.publish(thread_id, {"block_type": "end"})
            
        except Exception as e:
            self._logger.error(f"Error sending end block: {e}")
            raise

    class Response:
        def __init__(self, collector, tasks, async_service, logger):
            self._collector = collector
            self._tasks = tasks
            self._async_service = async_service
            self._logger = logger

        def __iter__(self):
            try:
                for msg in self._collector:
                    yield msg
                    if msg.get("block_type") == "end":
                        break
                        
            except Exception as e:
                self._logger.error(f"Error during sync collection: {e}")
                raise
                
            finally:
                # 清理所有任务
                with self._async_service.managed_sync() as loop:
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

        async def __aiter__(self):
            if self._is_closed:
                raise RuntimeError("Response already closed")
                
            try:
                async for msg in self._collector:
                    yield msg
                    if msg.get("block_type") == "end":
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
    