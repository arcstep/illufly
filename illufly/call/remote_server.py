import os
import logging
import json
import time
import uuid
import asyncio
import threading
import logging
from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from pathlib import Path

from ..mq import Publisher, Replier, DEFAULT_PUBLISHER
from ..mq.utils import cleanup_bound_socket
from ..async_utils import AsyncUtils
from .base_call import BaseCall

class RemoteServer(BaseCall):
    """远程服务器基类，提供请求-响应模式的服务"""
    
    def __init__(
        self,
        address: str,
        max_concurrent_tasks: int = 100,
        logger: Optional[logging.Logger] = None,
        publisher: Optional[Publisher] = None,
        service_name: str = None
    ):
        super().__init__(logger)
        self.address = address
        self.max_concurrent_tasks = max_concurrent_tasks
        self.publisher = publisher or DEFAULT_PUBLISHER
        self._server_task = None
        self._stop_event = asyncio.Event()
        self._ready_event = asyncio.Event()
        self._service_name = service_name or f"{self.__class__.__name__}.{self.__hash__()}"

        self._async_utils = AsyncUtils(logger=self._logger)
        self.register_method("handle_request", async_handle=self._async_handler)

    async def _async_handler(self, *args, thread_id: str, publisher: Publisher, **kwargs):
        """默认的请求处理方法，子类应该重写此方法"""
        raise NotImplementedError("Subclass must implement handle_request method")
    
    async def _start_server(self):
        """启动服务器的核心逻辑"""
        try:
            self._logger.info(f"Starting server at {self.address}")
            
            replier = Replier(
                address=self.address,
                max_concurrent_tasks=self.max_concurrent_tasks,
                logger=self._logger,
                publisher=self.publisher,
                service_name=self._service_name
            )
            
            self._ready_event.set()
            self._logger.info("Server is ready to accept connections")
            
            _, async_handler = self._methods["handle_request"]
            await replier.async_reply(async_handler)
            
        except Exception as e:
            self._logger.error(f"Server error: {e}", exc_info=True)
            raise
        finally:
            self._ready_event.clear()
    
    async def start(self):
        """启动服务器"""
        self._server_task = asyncio.create_task(self._start_server())
        try:
            await self._stop_event.wait()
        finally:
            await self.stop()
    
    async def stop(self):
        """停止服务器并清理资源"""
        self._stop_event.set()
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
            finally:
                self._server_task = None
                self._ready_event.clear()
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        asyncio.create_task(self.start())
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.stop()

    async def wait_until_ready(self, timeout: float = 5.0):
        """等待服务器就绪"""
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            self._logger.error("Server failed to start within timeout")
            return False
