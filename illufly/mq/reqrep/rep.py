from typing import AsyncGenerator, Callable, Awaitable, Any, Dict, List
from pydantic import BaseModel

from ..models import RequestBlock, ReplyBlock, ReplyAcceptedBlock, ReplyProcessingBlock, ReplyReadyBlock, ReplyState, RequestStep, ReplyErrorBlock
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
        self._active_tasks = 0
        self._tasks_lock = asyncio.Lock()

        self.to_binding()

    def to_binding(self):
        """初始化响应socket"""
        try:
            self._bound_socket = self._context.socket(zmq.REP)
            # 设置 HWM 为并发限制的 2 倍，确保有足够缓冲空间
            self._bound_socket.set_hwm(self._max_concurrent_tasks * 2)
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
                    request_data = await self._bound_socket.recv_json()
                    request_block = RequestBlock.model_validate(request_data)
                    thread_id = request_block.thread_id or self._get_thread_id()
                    
                    if request_block.request_step == RequestStep.INIT:
                        self._logger.info(f"Received INIT request for thread: {thread_id}")
                        await self._bound_socket.send_json(ReplyAcceptedBlock(
                            thread_id=thread_id,
                            subscribe_address=self._publisher._address
                        ).model_dump())
                        
                    elif request_block.request_step == RequestStep.READY:
                        async with self._tasks_lock:
                            current_tasks = len(self._pending_tasks)
                            self._logger.info(f"Received READY request for thread: {thread_id}, current tasks: {current_tasks}, max: {self._max_concurrent_tasks}")
                            
                            if current_tasks >= self._max_concurrent_tasks:
                                self._logger.warning(f"Max concurrent tasks reached: {current_tasks}/{self._max_concurrent_tasks}")
                                self._publisher.error(thread_id, "Max concurrent tasks reached")
                                await self._bound_socket.send_json(ReplyErrorBlock(
                                    thread_id=thread_id,
                                    error="Max concurrent tasks reached"
                                ).model_dump())
                                continue
                            
                            self._active_tasks += 1
                        
                        task = asyncio.create_task(
                            self._handle_request(
                                handler,
                                thread_id=thread_id,
                                args=request_block.args,
                                kwargs=request_block.kwargs
                            )
                        )
                        self._pending_tasks.add(task)
                        self._logger.info(f"Created task for thread: {thread_id}, pending tasks: {len(self._pending_tasks)}")
                        task.add_done_callback(self._task_done_callback)
                        
                        await self._bound_socket.send_json(ReplyProcessingBlock(
                            thread_id=thread_id
                        ).model_dump())
                    else:
                        raise ValueError(f"Invalid request step: {request_block.request_step}")

                except asyncio.CancelledError:
                    self._logger.info("Service cancelled, cleaning up")
                    raise
                except Exception as e:
                    self._logger.error(f"Unexpected error: {e}")
                    continue

        finally:
            await self._cleanup_tasks()
            self.cleanup()

    def _task_done_callback(self, task):
        """任务完成时的回调"""
        self._pending_tasks.discard(task)
        self._logger.info(f"Task completed, remaining tasks: {len(self._pending_tasks)}")
        asyncio.create_task(self._decrease_active_tasks())

    async def _decrease_active_tasks(self):
        """减少活跃任务计数"""
        async with self._tasks_lock:
            self._active_tasks -= 1
            self._logger.info(f"Active tasks decreased to: {self._active_tasks}")

    async def _cleanup_tasks(self):
        """清理所有pending任务"""
        if not self._pending_tasks:
            return

        self._logger.info(f"Cleaning up {len(self._pending_tasks)} pending tasks")
        for task in self._pending_tasks:
            if not task.done():
                task.cancel()

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
            if self._timeout:
                await asyncio.wait_for(
                    handler(*args, thread_id=thread_id, publisher=self._publisher, **kwargs),
                    timeout=self._timeout
                )
            else:
                await handler(*args, thread_id=thread_id, publisher=self._publisher, **kwargs)
        except asyncio.TimeoutError:
            self._publisher.error(thread_id, "Request timeout")
        except Exception as e:
            self._logger.error(f"Handler error: {e}")
            self._publisher.error(thread_id, str(e))
        finally:
            self._publisher.end(thread_id)

    def reply(self, handler: Callable[[Dict[str, Any]], Any]):
        """同步服务"""
        return self._async_utils.wrap_async_func(self.async_reply)(handler)
