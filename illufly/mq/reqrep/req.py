from typing import Optional, Dict, Any, List

from ..models import RequestBlock, ReplyBlock, ReplyState
from ..base_mq import BaseMQ

import zmq
import asyncio

class Requester(BaseMQ):
    """ZMQ REQ 请求者"""
    def __init__(self, address=None, logger=None):
        super().__init__(address, logger)
        self.to_connecting()

    def to_connecting(self):
        """初始化请求socket"""
        try:
            self._connected_socket = self._context.socket(zmq.REQ)
            self._connected_socket.connect(self._address)
            self._logger.info(f"Requester connected to: {self._address}")
        except Exception as e:
            self._logger.error(f"Connection error: {e}")
            raise

    async def async_request(self, thread_id: str, args: List[Any] = [], kwargs: Dict[str, Any] = {}, timeout: int = None) -> Optional[ReplyBlock]:
        """发送请求并等待响应"""
        if not self._connected_socket:
            raise RuntimeError("Requester not connected")

        try:
            # 发送请求
            request = RequestBlock(thread_id=thread_id, args=args, kwargs=kwargs)
            await self._connected_socket.send_json(request.model_dump())
            
            # 等待响应
            if await self._connected_socket.poll(timeout=timeout if timeout else None):
                reply = await self._connected_socket.recv_json()
                return ReplyBlock.model_validate(reply)
            else:
                self._logger.warning("Request timeout")
                return ReplyBlock(thread_id=thread_id, state=ReplyState.ERROR, result="Request timeout")
                
        except Exception as e:
            self._logger.error(f"Request failed: {e}")
            return ReplyBlock(thread_id=thread_id, state=ReplyState.ERROR, result=str(e))

    def request(self, thread_id: str, args: List[Any] = [], kwargs: Dict[str, Any] = {}, timeout: float = None) -> Optional[ReplyBlock]:
        """同步请求"""
        return self._async_utils.run_async(
            self.async_request(thread_id, args, kwargs, timeout)
        )

    def cleanup(self):
        """清理资源"""
        if self._connected_socket:
            self._connected_socket.close()
            self._connected_socket = None
            self._logger.debug("Requester socket closed")
