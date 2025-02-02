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

class ServiceDealer:
    """服务端 DEALER 实现，用于处理具体服务请求"""
    
    _registry = {}  # 类级别的服务注册表
    
    def __init__(
        self,
        router_address: str,
        service_id: str,
        context: Optional[zmq.asyncio.Context] = None,
        hwm: int = 1000,        # 网络层面的背压控制
        max_concurrent: int = 100,  # 应用层面的背压控制
        logger = None
    ):
        self._router_address = router_address
        self._service_id = service_id
        self._hwm = hwm
        self._max_concurrent = max_concurrent
        self._logger = logger or logging.getLogger(__name__)
        
        self._context = context or zmq.asyncio.Context()
        self._socket = None
        self._running = False
        self._heartbeat_task = None
        self._process_messages_task = None  # 添加新的任务引用
        self._semaphore = None
        self._pending_tasks = set()
        
        # 从类注册表中复制服务方法到实例，只保留元数据
        self._handlers = {}
        for name, info in self.__class__._registry.items():
            self._handlers[name] = {
                'handler': getattr(self, info['method_name']),  # 实际处理方法
                'metadata': info['metadata']  # 方法元数据
            }

        # 注册系统方法，但不包含在服务发现中
        self._system_handlers = {
            'register': {
                'handler': self._handle_register,
                'metadata': {'system': True, 'stream': False},
            },
            'heartbeat': {
                'handler': self._handle_heartbeat,
                'metadata': {'system': True, 'stream': False},
            }
        }

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
            self._socket.identity = self._service_id.encode()
            self._socket.set_hwm(self._hwm)
            
            # 尝试连接
            self._logger.info(f"Connecting to router at {self._router_address}")
            self._socket.connect(self._router_address)
            await asyncio.sleep(0.1)  # 给连接一点时间
            
            # 测试连接
            self._logger.info(f"Testing connection for service {self._service_id}")
            await self._socket.send_multipart([b"ping"])
            try:
                await asyncio.wait_for(self._socket.recv_multipart(), timeout=1.0)
                self._logger.info("Connection established")
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
        
        # 取消心跳任务
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # 取消消息处理任务
        if self._process_messages_task:
            self._process_messages_task.cancel()
            try:
                await self._process_messages_task
            except asyncio.CancelledError:
                pass
            self._process_messages_task = None
        
        # 等待所有挂起的任务完成
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
            self._pending_tasks.clear()
            
        if self._socket:
            self._socket.close()
            self._socket = None
            
        self._logger.info(f"Service {self._service_id} stopped")

    async def _register_to_router(self):
        """向路由器注册服务"""
        if not self._socket:
            return
        
        # 包含完整的方法元数据
        service_info = {
            method_name: handler['metadata']  # 使用完整的元数据
            for method_name, handler in self._handlers.items()
            if method_name not in self._system_handlers
        }
        
        self._logger.info(f"Registering service {self._service_id} with methods: {service_info}")
        await self._socket.send_multipart([
            b"register",
            json.dumps(service_info).encode()
        ])
        
        # 等待确认
        try:
            response = await asyncio.wait_for(
                self._socket.recv_multipart(),
                timeout=5.0
            )
            self._logger.info(f"Got registration response: {response}")
            if response[0] == b"ok":
                self._logger.info(f"Service {self._service_id} registered")
                return
            raise RuntimeError(f"Registration failed: {response}")
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
                self._logger.info(f"Received message: {multipart}")
                
                # 如果是请求消息（第一帧是客户端ID）
                if len(multipart) >= 2:
                    client_id = multipart[0]
                    request = deserialize_message(multipart[1])
                    
                    if isinstance(request, RequestBlock):
                        task = asyncio.create_task(self._process_request(client_id, request))
                        self._pending_tasks.add(task)
                        task.add_done_callback(self._pending_tasks.discard)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Message processing error: {e}", exc_info=True)

    async def _send_error(self, client_id: bytes, request_id: str, error_msg: str):
        """发送错误响应"""
        error = ErrorBlock(
            request_id=request_id,
            error=error_msg
        )
        await self._socket.send_multipart([
            client_id,
            serialize_message(error)
        ])

    async def _process_request(self, client_id: bytes, request: RequestBlock):
        """处理单个请求"""
        self._logger.info(f"Processing request: {request.func_name} from {client_id!r}")
        async with self._semaphore:
            try:
                # 先检查是否是系统方法
                if request.func_name in self._system_handlers:
                    handler = self._system_handlers[request.func_name]['handler']
                elif request.func_name in self._handlers:
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
                                client_id,
                                serialize_message(block)
                            ])
                        
                        # 发送结束标记
                        end_block = EndBlock(
                            request_id=request.request_id
                        )
                        await self._socket.send_multipart([
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
                            client_id,
                            serialize_message(reply)
                        ])
                    
                except Exception as e:
                    self._logger.error(f"Handler error: {e}", exc_info=True)
                    await self._send_error(client_id, request.request_id, str(e))
            except Exception as e:
                self._logger.error(f"Request processing error: {e}", exc_info=True)

    async def _send_heartbeat(self):
        """发送心跳"""
        while self._running:
            try:
                if self._socket:
                    await self._socket.send_multipart([b"heartbeat", b""])
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break  # 优雅地处理取消
            except Exception as e:
                self._logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(1.0)  # 错误后等待一段时间再重试

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

    async def _handle_register(self, *args, **kwargs):
        """处理注册请求"""
        return self._registry

    async def _handle_heartbeat(self, *args, **kwargs):
        """处理心跳请求"""
        return {'status': 'alive', 'timestamp': time.time()}
