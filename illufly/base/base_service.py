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

class BaseService(BaseCall, ABC):
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
    
    class Response:
        """包装响应，提供消息迭代能力"""
        def __init__(self, client_bus: MessageBus, thread_id: str):
            self.client_bus = client_bus
            self.thread_id = thread_id
            
        def __iter__(self):
            try:
                yield from self.client_bus.collect(self.thread_id)
            finally:
                self.client_bus.cleanup()            
            
    class AsyncResponse:
        """包装异步响应，提供异步消息迭代能力"""
        def __init__(self, client_bus: MessageBus, thread_id: str):
            self.client_bus = client_bus
            self.thread_id = thread_id
            
        async def __aiter__(self):
            async for msg in self.client_bus.async_collect(self.thread_id):
                yield msg
                
        def __del__(self):
            self.client_bus.cleanup()

    def __init__(self, service_name: str, message_bus_address: str = None, logger: logging.Logger = None):
        """初始化服务
        
        Args:
            service_name: 服务名称
            message_bus_address: MessageBus，如果为None则创建新的
            logger: 日志记录器
        """
        super().__init__(logger)

        self._message_bus_address = message_bus_address
        self._message_bus = MessageBus(
            address=message_bus_address,
            to_bind=True,
            to_connect=False,
            logger=logger
        )
        self._service_name = service_name or self.__class__.__name__
        self._async_service = AsyncService(logger)  # 创建单个 AsyncService 实例

    def __del__(self):
        """析构函数，确保资源被清理"""
        self._message_bus.cleanup()

    def __call__(self, *args, **kwargs):
        return self.call(*args, **kwargs)

    def _get_thread_id(self):
        return f"{self._service_name}.{uuid.uuid1()}"

    def call(self, **kwargs):
        """同步调用服务方法
        
        为每个调用创建独立的客户端消息总线，返回可迭代的响应对象。
        
        Args:
            **kwargs: 传递给服务方法的参数
            
        Returns:
            Response: 可迭代的响应对象
        """
        thread_id = self._get_thread_id()
        # 创建独立的客户端消息总线
        client_bus = MessageBus(
            address=self._message_bus_address,
            to_bind=False,
            to_connect=True,
            logger=self._logger
        )
        client_bus.subscribe(thread_id) 
        
        # 执行调用
        self.sync_method(
            "server", 
            thread_id=thread_id,
            message_bus=self._message_bus,
            **kwargs
        )
        client_bus.publish(thread_id, end=True)
        
        # 返回可迭代的响应对象
        return self.Response(client_bus, thread_id)

    async def async_call(self, **kwargs):
        """异步调用服务方法
        
        为每个调用创建独立的客户端消息总线，返回可异步迭代的响应对象。
        
        Args:
            **kwargs: 传递给服务方法的参数
            
        Returns:
            AsyncResponse: 可异步迭代的响应对象
        """
        thread_id = self._get_thread_id()
        # 创建独立的客户端消息总线
        client_bus = MessageBus(
            address=self._message_bus_address,
            to_bind=False,
            to_connect=True,
            logger=self._logger
        )
        client_bus.subscribe(thread_id) 
        # 执行调用
        await self.async_method(
            "server",
            thread_id=thread_id,
            message_bus=self._message_bus,
            **kwargs
        )
        client_bus.publish(thread_id, end=True)
        
        # 返回可异步迭代的响应对象
        return self.AsyncResponse(client_bus, thread_id)
    