import os
import logging
import json
import time
import uuid
import asyncio
import threading
import logging

from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator

from ..mq import Publisher, Replier
from ..mq.utils import cleanup_bound_socket
from .base_call import BaseCall

class RemoteServer(BaseCall):
    """
    远程服务端
    """

    def __init__(
        self,
        publisher_address: str,
        server_address: str,
        timeout: int = 30*1000,
        max_concurrent_tasks=100,
        service_name: str=None,
        logger: logging.Logger=None,
    ):
        """初始化服务
        
        Args:
            service_name: 服务名称
            publisher_address: 发布者地址
            server_address: 服务端地址
            timeout: 超时时间
            max_concurrent_tasks: 最大并发任务数
        """
        super().__init__(logger=logger)
        self._service_name = service_name or f"{self.__class__.__name__}.{self.__hash__()}"
        self._publisher_address = publisher_address
        self._server_address = server_address
        self._timeout = timeout
        self._max_concurrent_tasks = max_concurrent_tasks

        self.register_method("reply_handler", async_handle=self._async_handler)
        
        # 初始化服务端
        self._server = Replier(
            address=self._server_address,
            logger=self._logger,
            timeout=self._timeout,
            message_bus_address=self._publisher_address,
            max_concurrent_tasks=self._max_concurrent_tasks,
            service_name=self._service_name,
        )

        # 启动服务端
        self.start_server()

    async def _async_handler(self, *args, thread_id: str, publisher, **kwargs):
        """回复处理函数"""
        pass

    def start_server(self):
        """改进的服务启动方法"""
        try:
            async def _process(*args, thread_id: str, publisher: Publisher, **kwargs):
                return await self.async_method(
                    "reply_handler",
                    *args,
                    thread_id=thread_id,
                    publisher=publisher,
                    **kwargs
                )
            
            # 这里的任务创建后应该保存起来，以便后续管理
            self._server_task = asyncio.create_task(self._server.async_reply(_process))
            
        except Exception as e:
            self._logger.error(f"Error starting server: {e}")
            raise e

    async def stop_server(self):
        """添加停止服务的方法"""
        if hasattr(self, '_server_task'):
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
