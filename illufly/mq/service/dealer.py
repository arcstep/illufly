from typing import Dict, Any, Optional, Callable, Awaitable, AsyncGenerator, Union
import zmq
import zmq.asyncio
import asyncio
import logging
import json
import inspect
import uuid
import time

from functools import wraps
from pydantic import BaseModel
from ..models import (
    RequestBlock, ReplyBlock, StreamingBlock, EndBlock, 
    ErrorBlock, BlockType
)
from ..utils import serialize_message, deserialize_message

# 新增全局装饰器
def service_method(_func=None, *, name: str = None, **metadata):
    """支持两种调用方式的装饰器"""
    def decorator(func):
        # 分析方法类型
        is_coroutine = inspect.iscoroutinefunction(func)
        is_async_gen = inspect.isasyncgenfunction(func)
        is_generator = inspect.isgeneratorfunction(func)
        is_stream = is_generator or is_async_gen
        
        # 存储元数据（保持原有逻辑）
        func.__service_metadata__ = {
            'name': name or func.__name__,
            'stream': is_stream,
            'is_coroutine': is_coroutine,
            'is_async_gen': is_async_gen,
            'is_generator': is_generator,
            'metadata': metadata
        }
        
        # 保持包装逻辑
        if is_stream:
            @wraps(func)
            async def wrapper(self, *args, **kwargs):
                try:
                    if is_async_gen:
                        async for item in func(self, *args, **kwargs):
                            yield item
                    else:
                        for item in func(self, *args, **kwargs):
                            yield item
                            await asyncio.sleep(0)
                except Exception as e:
                    self._logger.error(f"<{getattr(self, '_service_name', '__class__.__name__')}> Stream handler error: {e}")
                    raise
            return wrapper
        
        if is_coroutine:
            @wraps(func)
            async def async_wrapper(self, *args, **kwargs):
                try:
                    return await func(self, *args, **kwargs)
                except Exception as e:
                    self._logger.error(f"<{getattr(self, '_service_name', '__class__.__name__')}> Handler error: {e}")
                    raise
            return async_wrapper
        
        return func
    
    # 处理无参数调用
    if _func is None:
        return decorator
    return decorator(_func)

class ServiceDealerMeta(type):
    """元类处理独立注册表"""
    def __new__(cls, name, bases, namespace):
        klass = super().__new__(cls, name, bases, namespace)
        
        # 创建独立注册表
        klass._registry = {}
        
        # 添加继承日志
        logging.debug(f"<{name}> Processing class: {name}")
        logging.debug(f"<{name}> Base classes: {[b.__name__ for b in bases]}")
        
        # 合并继承链（保持深度优先）
        for base in bases:
            if hasattr(base, '_registry'):
                logging.debug(f"<{name}> Inheriting from {base.__name__}: {base._registry.keys()}")
                klass._registry.update(base._registry.copy())
        
        # 收集当前类方法（兼容新旧装饰器）
        methods_found = []
        for attr_name in dir(klass):
            attr = getattr(klass, attr_name)
            if hasattr(attr, '__service_metadata__'):
                meta = attr.__service_metadata__
                methods_found.append(meta['name'])
                logging.debug(f"<{name}> Found service method: {attr_name} -> {meta['name']}")
                klass._registry[meta['name']] = {
                    'method_name': attr_name,
                    'stream': meta['stream'],
                    'is_coroutine': meta['is_coroutine'],
                    'is_async_gen': meta['is_async_gen'],
                    'is_generator': meta['is_generator'],
                    'metadata': meta['metadata']
                }
        
        logging.info(f"<{name}> Final registry: {klass._registry.keys()}")
        return klass

class ServiceDealer(metaclass=ServiceDealerMeta):
    """服务端 DEALER 实现，用于处理具体服务请求"""
    
    _registry = {}  # 保持原有类属性
    
    def __init__(
        self,
        router_address: str,
        context: Optional[zmq.asyncio.Context] = None,
        hwm: int = 1000,        # 网络层面的背压控制
        max_concurrent: int = 100,  # 应用层面的背压控制
        group: str = None,
        service_name: str = None
    ):
        self._router_address = router_address
        self._hwm = hwm
        self._max_concurrent = max_concurrent
        self._logger = logging.getLogger(__name__)
        self._service_name = service_name or self.__class__.__name__

        # 记录是否需要自行创建context
        self._create_own_context = context is None
        self._context = context or zmq.asyncio.Context()
        self._socket = None
        self._running = False
        self._heartbeat_task = None
        self._process_messages_task = None
        self._semaphore = None
        self._pending_tasks = set()
        self._current_load = 0
        self._is_overload = False
        self._heartbeat_interval = 10  # 将从 Router 配置中获取
        self._group = group or self._service_name
        
        # 从类注册表中复制服务方法到实例
        self._handlers = {}
        for name, info in self.__class__._registry.items():
            self._handlers[name] = {
                'handler': getattr(self, info['method_name']),
                'metadata': info['metadata']
            }

        # 生成一个随机的 UUID 作为服务标识
        self._service_id = str(uuid.uuid4())

        # 心跳状态跟踪
        self._last_successful_heartbeat = 0
        self._heartbeat_status = False  # 跟踪心跳状态，True表示连接正常
        self._heartbeat_sent_count = 0
        self._heartbeat_ack_count = 0

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
            self._logger.info(f"<{self._service_name}> Connecting to router at {self._router_address}")
            self._socket.connect(self._router_address)
            await asyncio.sleep(0.1)  # 给连接一点时间
            
            # 测试连接
            self._logger.info(f"<{self._service_name}> Testing connection for service {self._service_id}")
            await self._socket.send_multipart([
                b"ping",  # 消息类型
                b""      # 空负载
            ])
            try:
                response = await asyncio.wait_for(self._socket.recv_multipart(), timeout=1.0)
                if len(response) >= 2 and response[0] == b"ping_ack" and response[1] == b"pong":
                    self._logger.info(f"<{self._service_name}> Connection established")
                else:
                    raise RuntimeError(f"Invalid ping response: {response}")
            except asyncio.TimeoutError:
                raise RuntimeError(f"Failed to connect to router at {self._router_address}: connection test timeout")
            except Exception as e:
                raise RuntimeError(f"Failed to connect to router at {self._router_address}: {e}")
            
            # 继续初始化
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
            await self._register_to_router()
            self._heartbeat_task = asyncio.create_task(self._send_heartbeat(), name=f"{self._service_id}-heartbeat")
            self._process_messages_task = asyncio.create_task(self._process_messages(), name=f"{self._service_id}-process_messages")
            
            self._logger.info(f"<{self._service_name}> Service {self._service_id} started with {len(self._handlers)} methods")
            self._last_successful_heartbeat = time.time()
            self._heartbeat_check_task = asyncio.create_task(self._check_heartbeat_status())
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
                self._logger.info(f"<{self._service_name}> Sending shutdown request to router")
                await self._socket.send_multipart([
                    b"shutdown",
                    b""
                ])
                try:
                    self._logger.debug(f"<{self._service_name}> Waiting for shutdown acknowledgment")
                    multipart = await asyncio.wait_for(
                        self._socket.recv_multipart(),
                        timeout=0.5
                    )
                    if multipart[0] == b"shutdown_ack":
                        self._logger.info(f"<{self._service_name}> Received shutdown acknowledgment")
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

        self._logger.info(f"<{self._service_name}> Service stopped")

        if hasattr(self, '_heartbeat_check_task'):
            self._heartbeat_check_task.cancel()

    async def _register_to_router(self):
        """向Router注册服务信息"""
        try:
            # 创建一个可序列化的方法信息副本，移除方法对象
            serializable_methods = {}
            for method_name, method_info in self._handlers.items():
                # 只保留元数据，不包含实际方法对象
                serializable_methods[method_name] = {
                    'metadata': method_info['metadata']
                }
            
            # 构建服务信息
            service_info = {
                "group": self._group or self._service_name,
                "methods": serializable_methods,  # 使用可序列化的版本
                "max_concurrent": self._max_concurrent,
                "current_load": self._current_load,
                "request_count": 0,
                "reply_count": 0
            }
            
            self._logger.info(f"<{self._service_name}> Registering service with info: {service_info}")
            
            # 发送注册请求
            await self._socket.send_multipart([
                b"register",
                json.dumps(service_info).encode()
            ])
            
            # 等待注册响应
            multipart = await self._socket.recv_multipart()
            if len(multipart) < 2:
                raise ValueError(f"Invalid registration response: {multipart}")
            
            message_type = multipart[0]
            if message_type == b"error":
                error_message = multipart[1].decode() if len(multipart) > 1 else "Unknown error"
                raise ValueError(f"Registration rejected: {error_message}")
            
            # 接受'registered'或'register_ack'作为有效注册确认
            elif message_type != b"registered" and message_type != b"register_ack":
                raise ValueError(f"Unexpected registration response: {message_type}")
            
            # 注册成功，设置心跳间隔
            payload = json.loads(multipart[1].decode()) if len(multipart) > 1 and multipart[1] else {}
            self._heartbeat_interval = payload.get("heartbeat_interval", 10.0)
            self._last_successful_heartbeat = time.time()  # 初始化心跳时间
            self._heartbeat_status = True  # 初始化心跳状态为正常
            
            self._logger.info(f"<{self._service_name}> Service registered successfully. Using heartbeat interval: {self._heartbeat_interval}s")
            return True
        except Exception as e:
            self._logger.error(f"<{self._service_name}> Registration failed: {str(e)}", exc_info=True)
            return False

    async def _process_messages(self):
        """处理消息主循环"""
        while self._running:
            try:
                if not self._socket:
                    break
                    
                multipart = await self._socket.recv_multipart()
                
                # 如果是心跳确认消息，只在状态变化时打印，其他消息正常打印
                is_heartbeat_ack = len(multipart) >= 1 and multipart[0] == b'heartbeat_ack'
                
                # 只打印非心跳消息
                if not is_heartbeat_ack:
                    self._logger.debug(f"<{self._service_name}> DEALER Received message: {multipart}")
                
                if len(multipart) < 1:
                    self._logger.warning(f"<{self._service_name}> Received empty message")
                    continue
                    
                message_type = multipart[0]
                
                target_client_id = multipart[1]
                request = deserialize_message(multipart[-1]) if len(multipart) >= 3 else None
                if message_type == b"call_from_router" and isinstance(request, RequestBlock):
                    task = asyncio.create_task(self._process_request(target_client_id, request), name=f"{self._service_id}-{request.request_id}")
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
                elif message_type == b"heartbeat_ack":
                    # 更新最后成功心跳时间
                    self._heartbeat_ack_count += 1
                    self._last_successful_heartbeat = time.time()
                    
                    # 只在心跳状态变化时打印日志
                    if not self._heartbeat_status:
                        self._logger.info(f"<{self._service_name}> Heartbeat connection established with router")
                        self._heartbeat_status = True
                else:
                    self._logger.error(f"<{self._service_name}> DEALER Received unknown message type: {message_type}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"<{self._service_name}> Message processing error: {e}", exc_info=True)

    async def _process_request(self, target_client_id: bytes, request: RequestBlock):
        """处理单个请求"""
        self._logger.info(f"<{self._service_name}> DEALER Processing request: {request}")
        if self._current_load >= self._max_concurrent:
            await self._send_error(
                target_client_id,
                "Service overloaded"
            )
            self._logger.info(f"<{self._service_name}> DEALER Service overloaded, rejecting request from {self._service_id}")
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
                    func_name = request.func_name.split('.')[-1]
                    if func_name in self._handlers:
                        handler = self._handlers[func_name]['handler']
                        handler_info = self._registry[func_name]
                        is_stream = handler_info['stream']
                        is_coroutine = handler_info['is_coroutine']
                    else:
                        await self._send_error(
                            target_client_id,
                            f"Method {request.func_name} not found"
                        )
                        return

                    try:
                        if is_stream:
                            self._logger.info(f"<{self._service_name}> Streaming response for {request.func_name}")
                            # 处理流式响应
                            async for chunk in handler(*request.args, **request.kwargs):
                                # 使用工厂方法创建数据块
                                if isinstance(chunk, StreamingBlock):
                                    block = chunk
                                    block.request_id = request.request_id
                                else:
                                    block= chunk

                                await self._socket.send_multipart([
                                    b"reply_from_dealer",
                                    target_client_id,
                                    serialize_message(block)
                                ])
                            
                            # 发送结束标记
                            end_block = EndBlock(
                                request_id=request.request_id
                            )
                            await self._socket.send_multipart([
                                b"reply_from_dealer",
                                target_client_id,
                                serialize_message(end_block)
                            ])
                        else:
                            # 处理普通响应
                            if is_coroutine:
                                result = await handler(*request.args, **request.kwargs)
                            else:
                                result = handler(*request.args, **request.kwargs)
                            reply = ReplyBlock(
                                request_id=request.request_id,
                                result=result
                            )
                            await self._socket.send_multipart([
                                b"reply_from_dealer",
                                target_client_id,
                                serialize_message(reply)
                            ])
                        
                    except Exception as e:
                        self._logger.error(f"<{self._service_name}> DEALER Handler error: {e}", exc_info=True)
                        await self._send_error(target_client_id, str(e))
                except Exception as e:
                    self._logger.error(f"<{self._service_name}> DEALER Request processing error: {e}", exc_info=True)
        finally:
            self._current_load -= 1
            if self._current_load < 0:
                self._current_load = 0
            
            # 检查是否可以恢复服务
            if self._is_overload and self.check_can_resume():
                self._is_overload = False
                await self._socket.send_multipart([b"resume", b""])

    async def _send_error(self, target_client_id: bytes, error_msg: str):
        """发送错误响应"""
        error = ErrorBlock(
            error=error_msg
        )
        await self._socket.send_multipart([
            b"reply_from_dealer",
            target_client_id,
            serialize_message(error)
        ])

    async def _send_heartbeat(self):
        """发送心跳"""
        while self._running:
            try:
                if self._socket:
                    self._last_heartbeat_sent = time.time()
                    await self._socket.send_multipart([b"heartbeat", b""])
                    self._heartbeat_sent_count += 1
                    
                    # 每10次心跳打印一次诊断信息
                    if int(self._last_heartbeat_sent) % (10 * self._heartbeat_interval) < self._heartbeat_interval:
                        self._logger.debug(
                            f"<{self._service_name}> Heartbeat stats - sent: {self._heartbeat_sent_count}, " 
                            f"Heartbeat received: {self._heartbeat_ack_count}, "
                            f"status: {'active' if self._heartbeat_status else 'inactive'}")
                await asyncio.sleep(self._heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # 只在心跳状态变化时打印心跳发送失败
                if self._heartbeat_status:
                    self._logger.error(f"<{self._service_name}> Heartbeat send error: {e}")
                    self._heartbeat_status = False
                await asyncio.sleep(self._heartbeat_interval)

    async def _check_heartbeat_status(self):
        """检查心跳状态并在需要时重连"""
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        
        # 添加心跳发送后确认检查
        self._last_heartbeat_sent = 0
        
        while self._running:
            try:
                current_time = time.time()
                time_since_last_heartbeat = current_time - self._last_successful_heartbeat
                
                # 如果超过心跳超时时间的3倍，尝试重连
                if self._last_successful_heartbeat > 0 and time_since_last_heartbeat > self._heartbeat_interval * 3:
                    # 状态变化时才打印警告
                    if self._heartbeat_status:
                        self._logger.warning(
                            f"<{self._service_name}> No successful heartbeat for {time_since_last_heartbeat:.1f}s. "
                            f"Connection appears to be broken."
                        )
                        self._heartbeat_status = False
                    
                    # 尝试重连
                    if reconnect_attempts < max_reconnect_attempts:
                        self._logger.info(f"<{self._service_name}> Reconnection attempt {reconnect_attempts+1}/{max_reconnect_attempts}")
                        try:
                            # 关闭旧连接
                            if self._socket:
                                self._socket.close(linger=0)
                            
                            # 创建新连接 - 考虑创建新的context
                            if self._create_own_context:
                                # 可能需要重新创建context
                                self._context = zmq.asyncio.Context()
                            
                            self._socket = self._context.socket(zmq.DEALER)
                            self._socket.set_hwm(self._hwm)
                            self._socket.identity = self._service_id.encode()
                            
                            # 设置keep-alive选项
                            self._socket.setsockopt(zmq.TCP_KEEPALIVE, 1)
                            self._socket.setsockopt(zmq.TCP_KEEPALIVE_IDLE, 60)
                            self._socket.setsockopt(zmq.TCP_KEEPALIVE_INTVL, 10)
                            
                            # 连接到路由器
                            self._logger.debug(f"<{self._service_name}> Connecting to router at {self._router_address}")
                            self._socket.connect(self._router_address)
                            
                            # 重新注册服务
                            if await self._register_to_router():
                                # 成功重连后重置尝试计数
                                reconnect_attempts = 0
                                self._logger.info(f"<{self._service_name}> Successfully reconnected to router")
                            else:
                                raise Exception("Registration failed after reconnection")
                        except Exception as e:
                            reconnect_attempts += 1
                            self._logger.error(f"<{self._service_name}> Reconnection failed: {str(e)}", exc_info=True)
                    else:
                        self._logger.error(
                            f"<{self._service_name}> Failed to reconnect after {max_reconnect_attempts} attempts. "
                            f"Will continue trying with exponential backoff."
                        )
                        # 超过最大尝试次数后，采用指数退避策略继续尝试
                        await asyncio.sleep(min(30, 5 * (2 ** (reconnect_attempts - max_reconnect_attempts))))
                        
                        # 如果退避时间已经很长，重置尝试计数以避免无限等待
                        if reconnect_attempts > max_reconnect_attempts + 3:
                            reconnect_attempts = max_reconnect_attempts
                
                # 检查自上次发送心跳后是否有确认
                if self._last_heartbeat_sent > 0 and self._last_successful_heartbeat < self._last_heartbeat_sent:
                    time_since_send = current_time - self._last_heartbeat_sent
                    # 如果发送心跳后5秒仍没收到确认，认为连接有问题
                    if time_since_send > 5.0:
                        self._logger.warning(f"<{self._service_name}> Heartbeat sent but no acknowledgment received for {time_since_send:.1f}s")
                        # 强制重置心跳状态，触发重连
                        self._heartbeat_status = False
                        self._last_successful_heartbeat = 0
                
                await asyncio.sleep(min(5, self._heartbeat_interval / 2))
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"<{self._service_name}> Error in heartbeat check: {e}")
                await asyncio.sleep(5)

    def check_overload(self) -> bool:
        """检查是否接近满载（可重写）
        默认策略：当前负载达到最大并发的90%时认为即将满载
        """
        return self._current_load >= self._max_concurrent * 0.9

    def check_can_resume(self) -> bool:
        """检查是否可以恢复服务（可重写）
        默认策略：当前负载低于最大并发的80%时可以恢复
        """
        return self._current_load <= self._max_concurrent * 0.8
