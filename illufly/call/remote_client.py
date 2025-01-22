import os
import logging
import json
import time
import uuid
import asyncio
import threading

from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator

from ..mq import StreamingBlock, BlockType, Publisher, Requester, Subscriber, ReplyState
from .base_call import BaseCall

class RemoteClient(BaseCall):
    """
    远程客户端
    """

    def __init__(
        self,
        server_address: str = None,
        timeout: int = 30*1000,
        logger: logging.Logger=None,
    ):
        """初始化服务
        
        Args:
            server_address: 服务端地址
            timeout: 超时时间
        """
        super().__init__(logger=logger)
        self._server_address = server_address
        self._timeout = timeout
        self._logger.info(f"Initialized RemoteClient with server_address={self._server_address}")
        
        if self._server_address:
            self._server = Requester(
                address=self._server_address,
                logger=self._logger,
                timeout=self._timeout
            )
        else:
            raise ValueError("server_address is required")

    def __call__(self, *args, **kwargs):
        return self.call(*args, **kwargs)

    def call(self, *args, **kwargs):
        """同步调用服务方法"""
        return self._server.request(
            args=args,
            kwargs=kwargs
        )

    async def async_call(self, *args,  **kwargs):
        """异步调用服务方法"""
        return self._server.async_request(
                args=args,
                kwargs=kwargs
            )
