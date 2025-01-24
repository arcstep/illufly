import logging
from typing import Optional

from ..mq.reqrep import Requester
from .base_call import BaseCall

class RemoteClient(BaseCall):
    def __init__(
        self, 
        server_address: str,
        timeout: int = 30*1000,
        logger: Optional[logging.Logger] = None
    ):
        super().__init__(logger=logger)
        self.server_address = server_address
        self.timeout = timeout
        self._requester = Requester(address=server_address, timeout=self.timeout)

    def __call__(self, *args, **kwargs):
        """使对象可调用，默认使用同步调用"""
        return self.call(*args, **kwargs)

    async def async_call(self, *args, **kwargs):
        """异步调用远程服务"""
        return await self._requester.async_request(args=args, kwargs=kwargs)

    def call(self, *args, **kwargs):
        """同步调用远程服务"""
        return self._requester.request(args=args, kwargs=kwargs)

    async def cleanup(self):
        """清理资源"""
        if self._requester:
            self._requester.cleanup()
            self._requester = None
