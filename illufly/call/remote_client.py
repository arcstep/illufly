import os
import logging
import json
import time
import uuid
import asyncio
import threading

from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator

from ..mq import StreamingBlock, BlockType, Publisher, Requester, Subscriber
from .base_call import BaseCall

class RemoteClient(BaseCall):
    """远程客户端"""

    def __init__(
        self,
        service_name: str=None,
        subscriber_address: str = None,
        server_address: str = None,
        timeout: float = 30.0,
        poll_interval: int = 500,
        **kwargs
    ):
        """初始化服务
        
        Args:
            service_name: 服务名称
            subscriber_address: 订阅者地址
            server_address: 服务端地址
            timeout: 超时时间
            poll_interval: 轮询间隔(毫秒)，默认500ms
        """
        super().__init__(**kwargs)
        self._service_name = service_name or f"{self.__class__.__name__}.{self.__hash__()}"
        self._subscriber_address = subscriber_address
        self._server_address = server_address
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._logger.info(f"Initialized RemoteClient with service_name={self._service_name}, subscriber_address={self._subscriber_address}, server_address={self._server_address}")
        
        if self._subscriber_address:
            self._subscriber = Subscriber(address=self._subscriber_address, logger=self._logger)
        else:
            raise ValueError("subscriber_address is required")
        
        if self._server_address:
            self._server = Requester(address=self._server_address, logger=self._logger)
        else:
            raise ValueError("server_address is required")

    def __call__(self, *args, **kwargs):
        return self.call(*args, **kwargs)

    def _get_thread_id(self):
        """生成唯一的线程ID"""
        return f"{self._service_name}.{uuid.uuid4()}"  # 使用uuid4而不是uuid1

    def call(self, *args, thread_id: str = None, **kwargs):
        """同步调用服务方法"""
        thread_id = thread_id or self._get_thread_id()
        
        subscriber = Subscriber(
            thread_id,
            address=self._subscriber_address,
            logger=self._logger,
            poll_interval=self._poll_interval,
            timeout=self._timeout
        )
        
        try:
            response = self._server.request({
                "thread_id": thread_id,
                "args": args,
                "kwargs": kwargs
            })
            self._logger.info(f"Sync call response: {response}")
            return response
                
        except Exception as e:
            self._logger.error(f"Error in sync call: {e}")
            raise

    async def async_call(self, *args, thread_id: str = None, **kwargs):
        thread_id = thread_id or self._get_thread_id()
        
        subscriber = Subscriber(
            thread_id,
            address=self._subscriber_address,
            logger=self._logger,
            poll_interval=self._poll_interval,
            timeout=self._timeout
        )
        
        try:
            response = await self._server.async_request({
                "thread_id": thread_id,
                "args": args,
                "kwargs": kwargs
            })
            self._logger.info(f"Async call response: {response}")
            return response

        except Exception as e:
            self._logger.error(f"Error in async call: {e}")
            raise
