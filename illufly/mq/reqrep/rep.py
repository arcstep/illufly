from typing import AsyncGenerator, Callable, Awaitable, Any, Dict

from ..models import Request, Reply, ReplyState
from ..base_mq import BaseMQ

import asyncio
import zmq

class Replier(BaseMQ):
    """ZMQ REP 响应者
    """
    def __init__(self, address=None, logger=None):
        super().__init__(address, logger)
        self.to_binding()

    def to_binding(self):
        """初始化响应socket"""
        try:
            self._bound_socket = self._context.socket(zmq.REP)
            self._bound_socket.bind(self._address)
            self._logger.debug(f"Replier bound to {self._address}")
        except zmq.ZMQError as e:
            self._logger.error(f"Failed to bind replier socket: {e}")
            raise

    async def async_reply(self, handler: Callable[[Dict[str, Any]], Awaitable[Any]]):
        """开始服务，处理请求"""
        if not self._bound_socket:
            raise RuntimeError("Replier not bound")

        try:
            while True:
                try:
                    try:
                        # 等待请求
                        data = await self._bound_socket.recv_json()
                        request = Request.model_validate(data)
                        # 调用处理函数
                        result = await handler(*request.args, **request.kwargs)
                        response = Reply(thread_id=request.thread_id, state=ReplyState.SUCCESS, result=result)
                    except Exception as e:
                        self._logger.error(f"Handler error: {e}")
                        response = Reply(thread_id=request.thread_id, state=ReplyState.ERROR, result=str(e))                    
                    # 发送响应
                    await self._bound_socket.send_json(response.model_dump())
                    
                except zmq.ZMQError as e:
                    self._logger.error(f"ZMQ error: {e}")
                    break
                except Exception as e:
                    self._logger.error(f"Unexpected error: {e}")
                    continue
                    
        except asyncio.CancelledError:
            self._logger.debug("Service cancelled")
            raise
        finally:
            self.cleanup()

    def reply(self, handler: Callable[[Dict[str, Any]], Any]):
        """同步服务"""
        async def async_handler(data):
            return handler(data)
            
        return self._async_utils.run_async(
            self.async_reply(async_handler)
        )

    def cleanup(self):
        """清理资源"""
        if self._bound_socket:
            self._bound_socket.close()
            self._bound_socket = None
            self._logger.debug("Replier socket closed")
