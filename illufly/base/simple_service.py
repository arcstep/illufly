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
from ..mq import StreamingBlock, BlockType, Publisher, Subscriber, DEFAULT_PUBLISHER
from .base_call import BaseCall

class SimpleService(BaseCall):
    """同时包含服务端和客户端的简单服务结构"""

    def __init__(
        self,
        service_name: str=None,
        publisher_address: str = None,
        subscriber_address: str = None,
        timeout: float = 30.0,
        **kwargs
    ):
        """初始化服务
        
        Args:
            service_name: 服务名称
            publisher_address: 发布者地址
            subscriber_address: 订阅者地址
            timeout: 超时时间
        """
        super().__init__(**kwargs)
        self._service_name = service_name or f"{self.__class__.__name__}.{self.__hash__()}"
        self._publisher_address = publisher_address
        self._subscriber_address = subscriber_address
        self._timeout = timeout

        if self._publisher_address:
            self._publisher = Publisher(
                address=self._publisher_address,
                logger=self._logger
            )
        else:
            self._publisher = DEFAULT_PUBLISHER

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
        self._publisher.cleanup()

    async def _process_and_end(self, *args, thread_id: str, **kwargs):
        """将处理和结束标记合并为一个顺序任务"""
        self._logger.info(f"Starting _process_and_end for thread: {thread_id}")
        try:
            await self.async_method(
                "server",
                *args,
                thread_id=thread_id,
                message_bus=self._publisher,
                **kwargs
            )
        except Exception as e:
            self._logger.error(f"Processing resulted in error state: {e}")
            self._publisher.publish(
                thread_id,
                StreamingBlock.create_error(
                    error=str(e),
                    topic=thread_id
                )
            )
        finally:
            self._publisher.publish(
                thread_id,
                StreamingBlock.create_end(thread_id)
            )
            self._logger.info(f"Send <<END>> flag for thread: {thread_id}")

    def call(self, *args, thread_id: str = None, **kwargs):
        """同步调用服务方法"""
        thread_id = thread_id or self._get_thread_id()
        subscriber = Subscriber(
            address=self._subscriber_address,
            logger=self._logger
        )
        
        try:
            # 1. 先订阅并创建收集器
            subscriber.subscribe(thread_id)
            collector = subscriber.collect(timeout=self._timeout)
            
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
            subscriber.cleanup()
            raise

    async def async_call(self, *args, thread_id: str = None, **kwargs):
        """异步调用服务方法"""
        thread_id = thread_id or self._get_thread_id()
        client_bus = MessageBus(
            address=self._message_bus_address,
            logger=self._logger
        )
        
        try:
            # 1. 先订阅并创建收集器
            client_bus.subscribe(thread_id)
            collector = client_bus.async_collect(timeout=self._timeout)
            
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
