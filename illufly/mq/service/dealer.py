from typing import Dict, Any, Optional, Callable, Awaitable, AsyncGenerator, Union
import zmq
import zmq.asyncio
import asyncio
import logging
import json
import inspect
from functools import wraps
from pydantic import BaseModel
from ..models import (
    RequestBlock, ReplyBlock, StreamingBlock, EndBlock, 
    ErrorBlock, ReplyState, BlockType, TextChunk
)
from .utils import serialize_message, deserialize_message
import time
import uuid

class ServiceDealer:
    """服务端 DEALER 实现，用于处理具体服务请求"""
    
    _registry = {}  # 类级别的服务注册表
    
    def __init__(
        self,
        router_address: str,
        context: Optional[zmq.asyncio.Context] = None,
        hwm: int = 1000,        # 网络层面的背压控制
        max_concurrent: int = 100,  # 应用层面的背压控制
        logger = None
    ):
        self._router_address = router_address
        self._hwm = hwm
        self._max_concurrent = max_concurrent
        self._logger = logger or logging.getLogger(__name__)
        
        self._context = context or zmq.asyncio.Context.instance()
        self._socket = None
        self._running = False
        self._heartbeat_task = None
        self._process_messages_task = None
        self._semaphore = None
        self._pending_tasks = set()
        self._current_load = 0
        self._is_overload = False
        self._router_config = None  # 存储从 Router 获取的配置
        self._heartbeat_interval = None  # 将从 Router 配置中获取
        
        # 从类注册表中复制服务方法到实例
        self._handlers = {}
        for name, info in self.__class__._registry.items():
            self._handlers[name] = {
                'handler': getattr(self, info['method_name']),
                'metadata': info['metadata']
            }

        # 生成一个随机的 UUID 作为服务标识
        self._service_id = str(uuid.uuid4())

    @classmethod
    def service_method(cls, name: str = None, **metadata):
        """服务方法装饰器"""
        def decorator(func):
            method_name = func.__name__
            service_name = name or method_name
            
            # 分析方法类型
            is_coroutine = inspect.iscoroutinefunction(func)
            is_async_gen = inspect.isasyncgenfunction(func)
            is_generator = inspect.isgeneratorfunction(func)
            is_stream = is_generator or is_async_gen
            
            # 在类的注册表中记录服务信息
            cls._registry[service_name] = {
                'method_name': method_name,
                'stream': is_stream,
                'is_coroutine': is_coroutine,
                'is_async_gen': is_async_gen,
                'is_generator': is_generator,
                'metadata': metadata
            }
            
            if is_stream:
                # 流式方法使用异步生成器包装
                @wraps(func)
                async def wrapper(self, *args, **kwargs):
                    if is_async_gen:
                        async for item in func(self, *args, **kwargs):
                            yield item
                    else:
                        for item in func(self, *args, **kwargs):
                            yield item
                            await asyncio.sleep(0)
            else:
                # 非流式方法使用普通异步函数包装
                @wraps(func)
                async def wrapper(self, *args, **kwargs):
                    if is_coroutine:
                        return await func(self, *args, **kwargs)
                    else:
                        return func(self, *args, **kwargs)
            
            return wrapper
        return decorator

    async def start(self):
        """启动服务"""
        if self._running:
            return

        try:
            self._running = True
            self._socket = self._context.socket(zmq.DEALER)
            self._socket.set_hwm(self._hwm)
            # 设置 UUID 作为 identity
            self._socket.identity = self._service_id.encode()
            
            # 连接到路由器
            self._logger.info(f"Connecting to router at {self._router_address}")
            self._socket.connect(self._router_address)
            await asyncio.sleep(0.1)  # 给连接一点时间
            
            # 测试连接
            self._logger.info(f"Testing connection for service {self._service_id}")
            await self._socket.send_multipart([
                b"ping",  # 消息类型
                b""      # 空负载
            ])
            try:
                response = await asyncio.wait_for(self._socket.recv_multipart(), timeout=1.0)
                if len(response) >= 2 and response[0] == b"ping_ack" and response[1] == b"pong":
                    self._logger.info("Connection established")
                else:
                    raise RuntimeError("Invalid ping response")
            except asyncio.TimeoutError:
                raise RuntimeError(f"Failed to connect to router at {self._router_address}: connection test timeout")
            except Exception as e:
                raise RuntimeError(f"Failed to connect to router at {self._router_address}: {e}")
            
            # 继续初始化
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
            await self._register_to_router()
            self._heartbeat_task = asyncio.create_task(self._send_heartbeat())
            self._process_messages_task = asyncio.create_task(self._process_messages())
            
            self._logger.info(f"Service {self._service_id} started with {len(self._handlers)} methods")
        except Exception as e:
            self._running = False
            if hasattr(self, '_socket'):
                self._socket.close()
            raise RuntimeError(f"Failed to start service: {e}") from e

    async def stop(self):
        """停止服务"""
        if not self._running:
            return
        
        self._running = False

        # 取消心跳任务协程
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # 取消所有挂起任务协程
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
            self._pending_tasks.clear()
        
        # 取消处理消息任务协程
        if self._process_messages_task:
            self._process_messages_task.cancel()
            try:
                await self._process_messages_task
            except asyncio.CancelledError:
                pass
            self._process_messages_task = None

        # 发送关闭请求
        if self._socket:
            error = None
            try:
                self._logger.info("Sending shutdown request to router")
                await self._socket.send_multipart([
                    b"shutdown",
                    b""
                ])
                try:
                    self._logger.debug("Waiting for shutdown acknowledgment")
                    multipart = await asyncio.wait_for(
                        self._socket.recv_multipart(),
                        timeout=0.5
                    )
                    if multipart[0] == b"shutdown_ack":
                        self._logger.info("Received shutdown acknowledgment")
                    else:
                        error = "Invalid shutdown acknowledgment"
                except asyncio.TimeoutError:
                    error = "Shutdown acknowledgment timeout"
            except Exception as e:
                error = f"Error sending shutdown notice: {e}"
            finally:
                if error:
                    self._logger.error(error)

        # 关闭 socket
        if self._socket:
            self._socket.close()
            self._socket = None

        self._logger.info("Service stopped")

    async def _register_to_router(self):
        """向路由器注册服务"""
        if not self._socket:
            return
        
        # 包含服务配置信息
        service_info = {
            'methods': {
                method_name: handler['metadata']
                for method_name, handler in self._handlers.items()
            },
            'max_concurrent': self._max_concurrent,
            'current_load': self._current_load,
            'request_count': 0,
            'reply_count': 0,
        }
        
        self._logger.info(f"Registering service with info: {service_info}")
        await self._socket.send_multipart([
            b"register",
            json.dumps(service_info).encode()
        ])
        
        try:
            response = await asyncio.wait_for(
                self._socket.recv_multipart(),
                timeout=5.0
            )
            if len(response) >= 2 and response[0] == b"register_ack":
                router_config = json.loads(response[1].decode())
                self._heartbeat_interval = router_config.get('heartbeat_interval', 1.0) 
                self._logger.info(
                    f"Service registered successfully. "
                    f"Using heartbeat interval: {self._heartbeat_interval}s"
                )
                return
            raise RuntimeError(f"Invalid registration response: {response}")
        except Exception as e:
            self._logger.error(f"Registration failed: {e}")
            raise

    async def _process_messages(self):
        """处理消息主循环"""
        while self._running:
            try:
                if not self._socket:
                    break
                    
                multipart = await self._socket.recv_multipart()
                self._logger.info(f"DEALER Received message: {multipart}")


                # 正确的格式应当是
                # multipart[0] 消息类型，目前全部为 b'reply'
                # multipart[1] 客户端ID
                # multipart[2] 方法名称
                # multipart[3] RequestBlock（也包含了方法名称）
                client_id = multipart[1]
                request = deserialize_message(multipart[-1]) if len(multipart) >= 3 else None                
                if isinstance(request, RequestBlock):
                    task = asyncio.create_task(self._process_request(client_id, request))
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
                else:
                    self._logger.error(f"DEALER Received unknown message type: {message_type}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Message processing error: {e}", exc_info=True)

    async def _process_request(self, client_id: bytes, request: RequestBlock):
        """处理单个请求"""
        self._logger.info(f"DEALER Processing request: {request}")
        if self._current_load >= self._max_concurrent:
            await self._send_error(
                client_id, 
                request.request_id, 
                "Service overloaded"
            )
            self._logger.info(f"DEALER Service overloaded, rejecting request from {client_id}")
            return

        try:
            async with self._semaphore:
                self._current_load += 1
                
                # 检查是否需要报告即将满载
                if not self._is_overload and self.check_overload():
                    self._is_overload = True
                    await self._socket.send_multipart([b"overload", b""])
                
                try:
                    # 检查方法是否注册过
                    if request.func_name in self._handlers:
                        handler = self._handlers[request.func_name]['handler']
                        handler_info = self._registry[request.func_name]
                        is_stream = handler_info['stream']
                    else:
                        await self._send_error(
                            client_id,
                            request.request_id,
                            f"Method {request.func_name} not found"
                        )
                        return

                    try:
                        if is_stream:
                            self._logger.info(f"Streaming response for {request.func_name}")
                            # 处理流式响应
                            async for chunk in handler(*request.args, **request.kwargs):
                                # 使用工厂方法创建数据块
                                if isinstance(chunk, str):
                                    block = TextChunk(
                                        request_id=request.request_id,
                                        text=chunk
                                    )
                                elif isinstance(chunk, StreamingBlock):
                                    block = chunk
                                else:
                                    raise ValueError(f"Invalid chunk type: {type(chunk)}")

                                await self._socket.send_multipart([
                                    b"reply",
                                    client_id,
                                    serialize_message(block)
                                ])
                            
                            # 发送结束标记
                            end_block = EndBlock(
                                request_id=request.request_id
                            )
                            await self._socket.send_multipart([
                                b"reply",
                                client_id,
                                serialize_message(end_block)
                            ])
                        else:
                            # 处理普通响应
                            result = await handler(*request.args, **request.kwargs)
                            reply = ReplyBlock(
                                request_id=request.request_id,
                                state=ReplyState.READY,
                                result=result
                            )
                            await self._socket.send_multipart([
                                b"reply",
                                client_id,
                                serialize_message(reply)
                            ])
                        
                    except Exception as e:
                        self._logger.error(f"DEALER Handler error: {e}", exc_info=True)
                        await self._send_error(client_id, request.request_id, str(e))
                except Exception as e:
                    self._logger.error(f"DEALER Request processing error: {e}", exc_info=True)
        finally:
            self._current_load -= 1
            if self._current_load < 0:
                self._current_load = 0
            
            # 检查是否可以恢复服务
            if self._is_overload and self.check_can_resume():
                self._is_overload = False
                await self._socket.send_multipart([b"resume", b""])

    async def _send_error(self, client_id: bytes, request_id: str, error_msg: str):
        """发送错误响应"""
        error = ErrorBlock(
            request_id=request_id,
            error=error_msg
        )
        await self._socket.send_multipart([
            b"reply",
            client_id,
            serialize_message(error)
        ])

    async def _send_heartbeat(self):
        """发送心跳"""
        while self._running:
            try:
                if self._socket:
                    await self._socket.send_multipart([
                        b"heartbeat",
                        b"",
                    ])
                await asyncio.sleep(self._heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(self._heartbeat_interval)

    async def _handle_result(self, client_id: bytes, request_id: str, result: Any):
        """处理服务返回结果"""
        if isinstance(result, AsyncGenerator):
            try:
                async for chunk in result:
                    self._logger.info(f"Streaming chunk: {chunk}")
                    if isinstance(chunk, StreamingBlock):
                        block = chunk
                    else:
                        block = StreamingBlock.create_block(
                            block_type=BlockType.CONTENT,
                            request_id=request_id,
                            content=chunk
                        )
                    await self._send_message(client_id, block)
                
                # 发送结束标记
                end_block = EndBlock(request_id=request_id)
                await self._send_message(client_id, end_block)
            except Exception as e:
                await self._send_error(client_id, request_id, str(e))
        else:
            reply = ReplyBlock(
                request_id=request_id,
                state=ReplyState.READY,
                result=result
            )
            await self._send_message(client_id, reply)

    def check_overload(self) -> bool:
        """检查是否接近满载（可重写）
        默认策略：当前负载达到最大并发的90%时认为即将满载
        """
        return self._current_load >= self._max_concurrent

    def check_can_resume(self) -> bool:
        """检查是否可以恢复服务（可重写）
        默认策略：当前负载低于最大并发的80%时可以恢复
        """
        return self._current_load <= self._max_concurrent * 0.9
