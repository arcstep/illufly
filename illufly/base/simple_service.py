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
        address: str = None,
        timeout: float = 30.0,
        poll_interval: int = 500,
        **kwargs
    ):
        """初始化服务
        
        Args:
            service_name: 服务名称
            address: 发布和订阅的 ZMQ 地址
            subscriber_address: 订阅者地址
            timeout: 超时时间
            poll_interval: 轮询间隔(毫秒)，默认500ms
        """
        super().__init__(**kwargs)
        self._service_name = service_name or f"{self.__class__.__name__}.{self.__hash__()}"
        self._address = address
        self._timeout = timeout
        self._poll_interval = poll_interval

        # 使用新的 Publisher
        if self._address:
            self._publisher = Publisher(
                address=self._address,
                logger=self._logger
            )
        else:
            self._publisher = DEFAULT_PUBLISHER

        self._async_utils = AsyncUtils(logger=self._logger)
        self._processing_events = {}  # 用于跟踪每个调用的处理状态

        self.register_method("reply_handler", async_handle=self._async_handler)
    
    async def _async_handler(self, *args, thread_id: str, publisher, **kwargs):
        """回复处理函数"""
        pass

    def __del__(self):
        """析构函数，确保资源被清理"""
        self.cleanup()

    def __call__(self, *args, **kwargs):
        return self.call(*args, **kwargs)

    def _get_thread_id(self):
        """生成唯一的线程ID"""
        return f"{self._service_name}.{uuid.uuid4()}"  # 使用uuid4而不是uuid1

    def cleanup(self):
        """清理资源"""
        if hasattr(self, '_publisher') and self._address:
            self._publisher.cleanup()

    async def _process_and_end(self, *args, thread_id: str, **kwargs):
        """将处理和结束标记合并为一个顺序任务"""
        self._logger.info(f"Starting process for thread: {thread_id}")
        try:
            # 执行实际的服务方法
            await self.async_method(
                "reply_handler",
                *args,
                thread_id=thread_id,
                publisher=self._publisher,
                **kwargs
            )
        except Exception as e:
            self._logger.error(f"Processing error: {e}")
            self._publisher.publish(
                topic=thread_id,
                message=StreamingBlock.create_error(str(e))
            )
        finally:
            self._publisher.end(topic=thread_id)
            self._logger.info(f"Process finished for thread: {thread_id}")

    def call(self, *args, thread_id: str = None, **kwargs):
        """同步调用服务方法"""
        thread_id = thread_id or self._get_thread_id()
        
        # 创建订阅者
        subscriber = Subscriber(
            thread_id,
            address=self._address,
            logger=self._logger,
            poll_interval=self._poll_interval,
            timeout=self._timeout
        )
        
        try:
            # 创建处理任务
            with self._async_utils.managed_sync() as loop:
                task = loop.create_task(
                    self._process_and_end(
                        *args,
                        thread_id=thread_id,
                        **kwargs
                    )
                )
                
                # 直接返回订阅者的收集结果
                return subscriber.collect()
                
        except Exception as e:
            self._logger.error(f"Error in sync call: {e}")
            raise

    async def async_call(self, *args, thread_id: str = None, **kwargs):
        """异步调用服务方法"""
        thread_id = thread_id or self._get_thread_id()
        
        # 创建订阅者
        subscriber = Subscriber(
            thread_id,
            address=self._address,
            logger=self._logger,
            poll_interval=self._poll_interval,
            timeout=self._timeout
        )
        
        # 创建处理任务
        process_task = asyncio.create_task(
            self._process_and_end(
                *args,
                thread_id=thread_id,
                **kwargs
            )
        )
        
        try:
            # 收集结果
            async for msg in subscriber.async_collect():
                yield msg
                
            # 确保处理任务完成
            await process_task
            
        except Exception as e:
            self._logger.error(f"Call error: {e}")
            raise
        finally:
            if not process_task.done():
                process_task.cancel()
                try:
                    await process_task
                except asyncio.CancelledError:
                    pass
            
