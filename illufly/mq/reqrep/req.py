from typing import Optional, Dict, Any, List

from ..models import RequestBlock, ReplyBlock, ReplyState
from ..base_mq import BaseMQ

import zmq
import asyncio

class Requester(BaseMQ):
    """ZMQ REQ 请求者"""
    def __init__(self, address=None, logger=None, timeout: int=10*1000):
        super().__init__(address, logger)
        self._timeout = timeout
        self.to_connecting()

    def to_connecting(self):
        """初始化请求socket"""
        try:
            self._connected_socket = self._context.socket(zmq.REQ)
            self._connected_socket.setsockopt(zmq.RCVTIMEO, self._timeout)
            self._connected_socket.connect(self._address)
            self._logger.info(f"Requester connected to: {self._address}")
        except Exception as e:
            self._logger.error(f"Connection error: {e}")
            raise

    async def async_request(self, thread_id: str, args: List[Any] = [], kwargs: Dict[str, Any] = {}) -> Optional[ReplyBlock]:
        """发送请求并等待响应"""
        if not self._connected_socket:
            raise RuntimeError("Requester not connected")

        try:
            try:
                # 发送请求
                request = RequestBlock(thread_id=thread_id, args=args, kwargs=kwargs)
                await self._connected_socket.send_json(request.model_dump())
                # 等待响应
                reply = await self._connected_socket.recv_json()
                return ReplyBlock.model_validate(reply)

            except zmq.error.ZMQError as e:
                if e.errno == zmq.EAGAIN:
                    # ZMQ 接收超时
                    timeout_info = f"Request timeout after {self._timeout} ms"
                    self._logger.warning(timeout_info)
                    return ReplyBlock(thread_id=thread_id, state=ReplyState.ERROR, result=timeout_info)
                else:
                    raise
                
        except Exception as e:
            self._logger.error(f"Request failed: {e}")
            return ReplyBlock(thread_id=thread_id, state=ReplyState.ERROR, result=str(e))

    def request(self, thread_id: str, args: List[Any] = [], kwargs: Dict[str, Any] = {}) -> Optional[ReplyBlock]:
        """同步请求"""
        return self._async_utils.run_async(
            self.async_request(thread_id, args, kwargs)
        )

    def cleanup(self):
        """清理资源"""
        if self._connected_socket:
            self._connected_socket.close()
            self._connected_socket = None
            self._logger.debug("Requester socket closed")
