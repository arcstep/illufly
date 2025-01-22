from typing import AsyncGenerator, Callable, Awaitable, Any, Dict, List
from pydantic import BaseModel

from ..models import RequestBlock, ReplyBlock, ReplyAcceptedBlock, ReplyProcessingBlock, ReplyReadyBlock, ReplyState, RequestStep
from ..base_mq import BaseMQ
from ..pubsub import Publisher, DEFAULT_PUBLISHER
from ..utils import cleanup_bound_socket

import asyncio
import zmq
import uuid

class Replier(BaseMQ):
    """ZMQ REP 响应者
    """
    def __init__(self, address=None, message_bus_address=None, logger=None, timeout=None, service_name=None):
        super().__init__(address, logger)
        self.to_binding()
        self._timeout = timeout
        self._service_name = service_name or f"service_{self.__hash__()}"
        self._message_bus_address = message_bus_address
        if self._message_bus_address:
            self._publisher = Publisher(address=self._message_bus_address, logger=self._logger)
        else:
            self._publisher = DEFAULT_PUBLISHER

    def to_binding(self):
        """初始化响应socket"""
        try:
            self._bound_socket = self._context.socket(zmq.REP)
            self._bound_socket.bind(self._address)
            self._logger.debug(f"Replier bound to {self._address}")
        except zmq.ZMQError as e:
            self._logger.error(f"Failed to bind replier socket: {e}")
            raise

    def _get_thread_id(self):
        """生成唯一的线程ID"""
        return f"{self._service_name}.{uuid.uuid4()}"  # 使用uuid4而不是uuid1

    async def async_reply(self, handler: Callable[[Dict[str, Any]], Awaitable[Any]]):
        """开始服务，处理请求"""
        if not self._bound_socket:
            raise RuntimeError("Replier not bound")

        try:
            async def _recv_request():
                request_data = await self._bound_socket.recv_json()
                request_block = RequestBlock.model_validate(request_data)
                self._logger.debug(f"Received request: {request_block}")
                return request_block

            async def _send_reply(model_data: BaseModel):
                await self._bound_socket.send_json(model_data.model_dump())
                self._logger.debug(f"Sent reply: {model_data}")

            while True:
                try:
                    # 等待请求
                    request_block = await _recv_request()
                    thread_id = request_block.thread_id or self._get_thread_id()
                    if request_block.request_step == RequestStep.INIT:
                        # 回复处理的线程和用于消息订阅的地址
                        await _send_reply(ReplyAcceptedBlock(
                            thread_id=thread_id,
                            subscribe_address=self._publisher._address
                        ))
                    elif request_block.request_step == RequestStep.READY:
                        # 这里是一个慢处理，因此需要使用非阻塞模式
                        asyncio.create_task(
                            self._handle_request(
                                handler,
                                thread_id=thread_id,
                                args=request_block.args,
                                kwargs=request_block.kwargs
                            ))
                        await _send_reply(ReplyProcessingBlock(thread_id=thread_id))
                    else:
                        raise ValueError(f"Invalid request step: {request_block.request_step}")
                    
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

    async def _handle_request(self, handler: Callable, thread_id: str, args: List[Any], kwargs: Dict[str, Any]):
        """异步处理请求"""
        try:
            self._logger.debug(f"Handling request: {thread_id}, {args}, {kwargs}")
            await handler(*args, thread_id=thread_id, publisher=self._publisher, **kwargs)
        except Exception as e:
            self._logger.error(f"Handler error: {e}")
            self._publisher.error(thread_id, str(e))
        finally:
            self._publisher.end(thread_id)

    def reply(self, handler: Callable[[Dict[str, Any]], Any]):
        """同步服务"""
        return self._async_utils.wrap_async_func(self.async_reply)(handler)

    def cleanup(self):
        """清理资源"""
        cleanup_bound_socket(self._bound_socket, self._address, self._logger)

        if self._publisher and self._publisher != DEFAULT_PUBLISHER:
            self._publisher.cleanup()
