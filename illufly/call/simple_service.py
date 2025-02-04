import os
import logging
import json
import time
import uuid
import asyncio
import threading

from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator

from ..async_utils import AsyncUtils
from ..mq import StreamingBlock, BlockType, Publisher, Subscriber, DEFAULT_PUBLISHER
from .base_call import BaseCall

class SimpleService(BaseCall):
    """同时包含服务端和客户端的简单服务结构"""

    def __init__(
        self,
        service_name: str=None,
        publisher: Publisher = None,
        timeout: int = 30*1000,
        **kwargs
    ):
        """初始化服务
        
        Args:
            service_name: 服务名称
            publisher: 发布者
            timeout: 超时时间
        """
        super().__init__(**kwargs)
        self._service_name = service_name or f"{self.__class__.__name__}.{self.__hash__()}"
        self._publisher = publisher or DEFAULT_PUBLISHER
        self._timeout = timeout
        self._tasks = set()
        self._logger.info(f"SimpleService initialized with service_name={service_name}, address={self._publisher._address}")
        
        self._async_utils = AsyncUtils(logger=self._logger)
        self._processing_events = {}  # 用于跟踪每个调用的处理状态

        self.register_method("reply_handler", async_handle=self._async_handler)
    
    async def _async_handler(self, *args, request_id: str, publisher, **kwargs):
        """回复处理函数"""
        pass

    def __del__(self):
        """析构函数"""
        self._logger.info("SimpleService being destroyed")
        try:
            self.cleanup()
        except Exception as e:
            self._logger.info(f"Error during cleanup in __del__: {e}")

    def __call__(self, *args, **kwargs):
        return self.call(*args, **kwargs)

    def _get_request_id(self):
        """生成唯一的线程ID"""
        return f"{self._service_name}.{uuid.uuid4()}"  # 使用uuid4而不是uuid1

    def cleanup(self):
        """清理资源"""
        try:
            loop = asyncio.get_running_loop()
            if not loop.is_closed():
                for task in self._tasks:
                    if not task.done():
                        task.cancel()
        except RuntimeError as e:
            self._logger.info(f"No running event loop available: {e}")
        except Exception as e:
            self._logger.info(f"Error during cleanup: {e}")
        finally:
            if self._publisher._address != DEFAULT_PUBLISHER._address and hasattr(self, '_publisher'):
                self._publisher.cleanup()

    async def _process_and_end(self, *args, request_id: str, **kwargs):
        """将处理和结束标记合并为一个顺序任务"""
        task_id = id(asyncio.current_task())
        self._logger.info(f"Process task {task_id} starting for thread {request_id}")
        try:
            # 执行实际的服务方法
            await self.async_method(
                "reply_handler",
                *args,
                request_id=request_id,
                publisher=self._publisher,
                **kwargs
            )
        except Exception as e:
            self._logger.error(f"Process task {task_id} failed with error: {e}")
            self._publisher.error(request_id=request_id, error=str(e))
        finally:
            self._publisher.end(request_id=request_id)

    def call(self, *args, request_id: str = None, **kwargs):
        """同步调用服务方法"""
        request_id = request_id or self._get_request_id()        
        subscriber = Subscriber(
            request_id,
            address=self._publisher._address,
            logger=self._logger,
            timeout=self._timeout
        )
        
        try:
            with self._async_utils.managed_sync() as loop:
                task = loop.create_task(
                    self._process_and_end(
                        *args,
                        request_id=request_id,
                        **kwargs
                    )
                )
                self._tasks.add(task)                
                task.add_done_callback(self._tasks.discard)
                subscriber.on_exit = lambda: task.cancel()
                return subscriber
                
        except Exception as e:
            self._logger.error(f"Error in sync call: {e}")
            raise

    async def async_call(self, *args, request_id: str = None, **kwargs):
        request_id = request_id or self._get_request_id()        
        subscriber = Subscriber(
            request_id,
            address=self._publisher._address,
            logger=self._logger,
            timeout=self._timeout
        )
        
        task = asyncio.create_task(
            self._process_and_end(
                *args,
                request_id=request_id,
                **kwargs
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        subscriber.on_exit = lambda: task.cancel()        
        return subscriber
