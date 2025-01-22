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
    def __init__(self, address=None, message_bus_address=None, logger=None, timeout=None, max_concurrent_tasks=None, service_name=None):
        super().__init__(address, logger)
        self.to_binding()
        self._timeout = timeout
        self._max_concurrent_tasks = max_concurrent_tasks or 10
        self._service_name = service_name or f"service_{self.__hash__()}"

        self._message_bus_address = message_bus_address
        if self._message_bus_address:
            self._publisher = Publisher(address=self._message_bus_address, logger=self._logger)
        else:
            self._publisher = DEFAULT_PUBLISHER

        self._task_semaphore = asyncio.Semaphore(self._max_concurrent_tasks)
        self._pending_tasks = set()  # 跟踪所有pending的任务

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
            while True:
                try:
                    # 等待请求
                    request_data = await self._bound_socket.recv_json()
                    request_block = RequestBlock.model_validate(request_data)
                    self._logger.debug(f"Received request: {request_block}")

                    thread_id = request_block.thread_id or self._get_thread_id()
                    
                    if request_block.request_step == RequestStep.INIT:
                        await self._bound_socket.send_json(ReplyAcceptedBlock(
                            thread_id=thread_id,
                            subscribe_address=self._publisher._address
                        ).model_dump())
                    elif request_block.request_step == RequestStep.READY:
                        # 创建并跟踪任务
                        task = asyncio.create_task(
                            self._handle_request(
                                handler,
                                thread_id=thread_id,
                                args=request_block.args,
                                kwargs=request_block.kwargs
                            )
                        )
                        self._pending_tasks.add(task)
                        task.add_done_callback(self._pending_tasks.discard)
                        
                        await self._bound_socket.send_json(ReplyProcessingBlock(
                            thread_id=thread_id
                        ).model_dump())
                    else:
                        raise ValueError(f"Invalid request step: {request_block.request_step}")

                except asyncio.CancelledError:
                    self._logger.debug("Service cancelled")
                    raise  # 直接抛出取消异常，让 finally 处理清理
                except Exception as e:
                    self._logger.error(f"Unexpected error: {e}")
                    continue

        finally:
            # 在 finally 中处理所有清理工作
            await self._cleanup_tasks()  # 等待或取消所有任务
            self.cleanup()  # 清理其他资源

    async def _cleanup_tasks(self):
        """清理所有pending任务"""
        if not self._pending_tasks:
            return

        # 取消所有任务
        for task in self._pending_tasks:
            if not task.done():
                task.cancel()

        # 等待所有任务完成
        await asyncio.gather(*self._pending_tasks, return_exceptions=True)
        self._pending_tasks.clear()

    def cleanup(self):
        """清理资源"""
        if self._bound_socket:
            self._bound_socket.close()
            self._bound_socket = None
            self._logger.debug("Replier socket closed")

        if self._publisher and self._publisher != DEFAULT_PUBLISHER:
            self._publisher.cleanup()

    def __del__(self):
        """析构函数"""
        self.cleanup()

    async def _handle_request(self, handler: Callable, thread_id: str, args: List[Any], kwargs: Dict[str, Any]):
        """异步处理请求"""
        try:
            async with self._task_semaphore:  # 使用信号量控制并发
                self._logger.debug(f"Handling request: {thread_id}")
                await handler(*args, thread_id=thread_id, publisher=self._publisher, **kwargs)
        except asyncio.CancelledError:
            self._logger.debug(f"Task cancelled: {thread_id}")
            raise
        except Exception as e:
            self._logger.error(f"Handler error: {e}")
            self._publisher.error(thread_id, str(e))
        finally:
            self._publisher.end(thread_id)

    def reply(self, handler: Callable[[Dict[str, Any]], Any]):
        """同步服务"""
        return self._async_utils.wrap_async_func(self.async_reply)(handler)
