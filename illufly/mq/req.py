from typing import Optional, Dict, Any

from .models import StreamingBlock
from .base import BaseMQ

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

    async def async_request(self, data: Dict[str, Any], timeout: float = None) -> Optional[StreamingBlock]:
        """发送请求并等待响应"""
        if not self._connected_socket:
            raise RuntimeError("Requester not connected")

        try:
            # 发送请求
            message = StreamingBlock.create_chunk(content=data)
            await self._connected_socket.send_string(message.model_dump_json())
            
            # 等待响应
            if await self._connected_socket.poll(timeout=timeout * 1000 if timeout else None):
                response = await self._connected_socket.recv_string()
                return StreamingBlock.model_validate_json(response)
            else:
                self._logger.warning("Request timeout")
                return StreamingBlock.create_error("Request timeout")
                
        except Exception as e:
            self._logger.error(f"Request failed: {e}")
            return StreamingBlock.create_error(str(e))

    def request(self, data: Dict[str, Any], timeout: float = None) -> Optional[StreamingBlock]:
        """同步请求"""
        return self._async_utils.run_async(
            self.async_request(data, timeout=timeout)
        )

    def cleanup(self):
        """清理资源"""
        if self._connected_socket:
            self._connected_socket.close()
            self._connected_socket = None
            self._logger.debug("Requester socket closed")
