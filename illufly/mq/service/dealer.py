from typing import Dict, Any, Optional, Callable, Awaitable, AsyncGenerator, Union
import zmq
import zmq.asyncio
import asyncio
import logging
import json
import inspect
import uuid
import time
from enum import Enum

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

class DealerState(Enum):
    INIT = 0       # 初始化状态
    RUNNING = 1    # 正常运行
    RECONNECTING = 2 # 重连中
    STOPPING = 3   # 停止中
    STOPPED = 4    # 已停止

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
        service_name: str = None,
        heartbeat_interval: float = 0.5,
        heartbeat_timeout: float = 5.0,
        service_id: str = None
    ):
        self._router_address = router_address
        self._hwm = hwm
        self._max_concurrent = max_concurrent
        self._logger = logging.getLogger(__name__)
        self._service_name = service_name or self.__class__.__name__

        # 记录是否需要自行创建context
        self._context = context or zmq.asyncio.Context()
        self._socket = None
        self._heartbeat_task = None
        self._process_messages_task = None
        self._semaphore = None
        self._pending_tasks = set()
        self._current_load = 0
        self._is_overload = False
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._group = group or self._service_name
        
        # 从类注册表中复制服务方法到实例
        self._handlers = {}
        for name, info in self.__class__._registry.items():
            self._handlers[name] = {
                'handler': getattr(self, info['method_name']),
                'metadata': info['metadata']
            }

        # 生成一个随机的 UUID 作为服务标识
        self._service_id = service_id or f'{self._service_name}-{str(uuid.uuid4().hex[:8])}'

        # 状态管理
        self._state = DealerState.INIT
        self._state_lock = asyncio.Lock()  # 状态锁
        self._reconnect_in_progress = False
        
        # 心跳状态
        self._last_successful_heartbeat = time.time()
        self._heartbeat_status = False
        self._reconnect_count = 0
        self._max_reconnect_attempts = 10

    async def _force_reconnect(self):
        """强制完全重置连接"""
        self._logger.info("Initiating forced reconnection...")
        
        # 重新初始化socket
        self._socket = self._context.socket(zmq.DEALER)
        self._socket.identity = self._service_id.encode()
        self._socket.set_hwm(self._hwm)
        self._socket.setsockopt(zmq.LINGER, 0)  # 设置无等待关闭
        self._socket.setsockopt(zmq.IMMEDIATE, 1)  # 禁用缓冲
        self._socket.connect(self._router_address)
        
        # 重置心跳状态
        self._last_successful_heartbeat = time.time()
        self._heartbeat_sent_count = 0
        self._heartbeat_ack_count = 0
        self._heartbeat_status = True

    async def _reconnect(self):
        """尝试重新连接到路由器"""
        self._logger.info(f"<{self._service_id}> 开始执行重连...")
        
        try:
            # 关闭现有连接
            if self._socket and not self._socket.closed:
                self._socket.close()
            
            # 重新创建信号量
            if not hasattr(self, '_semaphore') or self._semaphore is None:
                self._logger.warning(f"<{self._service_id}> 信号量为None，重新创建")
                self._semaphore = asyncio.Semaphore(self._max_concurrent)
            
            # 重新连接到路由器
            self._socket = self._context.socket(zmq.DEALER)
            self._socket.identity = self._service_id.encode()
            self._socket.set_hwm(self._hwm)
            self._socket.setsockopt(zmq.LINGER, 0)  # 设置无等待关闭
            self._socket.setsockopt(zmq.IMMEDIATE, 1)  # 禁用缓冲
            self._socket.connect(self._router_address)
            
            # 重置心跳状态
            self._last_successful_heartbeat = time.time()
            self._heartbeat_sent_count = 0
            self._heartbeat_ack_count = 0
            self._heartbeat_status = True

            # 重连状态
            self._reconnect_in_progress = False
            self._reconnect_attempts = 0
            self._max_reconnect_attempts = 5
            self._service_registered = False

            self._logger.info(f"<{self._service_id}> 重连成功")

            return True
            
        except Exception as e:
            self._logger.error(f"<{self._service_id}> 重连过程中发生错误: {e}", exc_info=True)
            
            # 确保信号量存在，防止任务崩溃
            if not hasattr(self, '_semaphore') or self._semaphore is None:
                self._semaphore = asyncio.Semaphore(self._max_concurrent)
            
            return False

    async def start(self):
        """启动服务"""
        async with self._state_lock:
            if self._state not in [DealerState.INIT, DealerState.STOPPED]:
                self._logger.warning(f"<{self._service_id}> Cannot start from {self._state} state")
                return False
                
            self._state = DealerState.RUNNING

        # 重建连接
        if not await self._reconnect():
            self._logger.error(f"<{self._service_id}> 网络连接失败")
            return False

        # 启动核心任务
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name=f"{self._service_id}-heartbeat")
        self._process_messages_task = asyncio.create_task(self._process_messages(), name=f"{self._service_id}-process_messages")
        self._reconnect_monitor_task = asyncio.create_task(self._reconnect_monitor(), name=f"{self._service_id}-reconnect_monitor")

        await self._register_to_router()

        self._logger.info(f"<{self._service_id}> Service {self._service_id} started with {len(self._handlers)} methods")
        self._last_successful_heartbeat = time.time()
        return True

    async def stop(self):
        """停止服务"""
        async with self._state_lock:
            if self._state == DealerState.STOPPED:
                return
                
            self._state = DealerState.STOPPING
            
        # 取消任务（注意顺序）
        tasks = []
        if self._process_messages_task:
            self._process_messages_task.cancel()
            self._service_registered = False
            tasks.append(self._process_messages_task)
            
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            tasks.append(self._heartbeat_task)
            
        if self._reconnect_monitor_task:
            self._reconnect_monitor_task.cancel()
            tasks.append(self._reconnect_monitor_task)
            
        # 等待所有任务取消完成
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        # 清理资源
        if self._socket:
            self._socket.close(linger=0)
            self._socket = None
            
        async with self._state_lock:
            self._state = DealerState.STOPPED
            self._logger.info(f"<{self._service_id}> Service stopped")

    async def _register_to_router(self):
        """向Router注册服务信息"""
        try:
            if not self._socket:
                return
            
            self._service_registered = True
            # 创建一个可序列化的方法信息副本，移除方法对象
            methods = {}
            for method_name, method_info in self._handlers.items():
                methods[method_name] = {
                    'metadata': method_info['metadata']
                }
            
            # 构建服务信息
            service_info = {
                "group": self._group or self._service_name,
                "methods": methods,  # 使用可序列化的版本
                "max_concurrent": self._max_concurrent,
                "current_load": self._current_load,
                "request_count": 0,
                "reply_count": 0
            }
            
            self._logger.info(f"<{self._service_id}> Registering service with info: {service_info}")
            
            # 发送注册请求
            await self._socket.send_multipart([
                b"register",
                json.dumps(service_info).encode()
            ])
        
        except asyncio.CancelledError:
            return
        except zmq.ZMQError as e:
            self._service_registered = False
            self._logger.error(f"<{self._service_id}> Registration failed: {str(e)}")
        except Exception as e:
            self._service_registered = False
            self._logger.error(f"<{self._service_id}> Registration failed: {str(e)}", exc_info=True)

    async def _process_messages(self):
        """处理消息主循环"""
        counter = 0
        while self._state == DealerState.RUNNING:
            try:
                await asyncio.sleep(0)
                if not self._socket:
                    break
                    
                multipart = await self._socket.recv_multipart()
                
                # 更新心跳状态
                self._heartbeat_status = True
                self._last_successful_heartbeat = time.time()
                self._reconnect_attempts = 0

                # 如果是心跳确认消息，只在状态变化时打印，其他消息正常打印
                is_heartbeat_ack = len(multipart) >= 1 and multipart[0] == b'heartbeat_ack'
                
                # 只打印非心跳消息
                if is_heartbeat_ack:
                    counter = counter + 1 if counter < 10 else 0
                    if counter == 0:
                        self._logger.info(f"<{self._service_id}> HEARTBEAT ACK")
                else:
                    self._logger.info(f"<{self._service_id}> DEALER Received message: {multipart}")
                
                if len(multipart) < 1:
                    self._logger.warning(f"<{self._service_id}> Received empty message")
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
                
                elif message_type == b"register_ack":
                    self._logger.info(f"<{self._service_id}> Service registered successfully.")
                
                elif message_type == b"error":
                    error_message = multipart[1].decode() if len(multipart) > 1 else "Unknown error"
                    self._logger.error(f"<{self._service_id}> error: {error_message}")

                else:
                    self._logger.error(f"<{self._service_id}> DEALER Received unknown message type: {message_type}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"<{self._service_id}> Message processing error: {e}", exc_info=True)

    async def _process_request(self, target_client_id: bytes, request: RequestBlock):
        """处理单个请求"""
        self._logger.info(f"<{self._service_id}> DEALER Processing request: {request}")
        if self._current_load >= self._max_concurrent:
            await self._send_error(
                target_client_id,
                "Service overloaded"
            )
            self._logger.info(f"<{self._service_id}> DEALER Service overloaded, rejecting request from {self._service_id}")
            return

        try:
            # 防止信号量为None导致崩溃
            if not hasattr(self, '_semaphore') or self._semaphore is None:
                self._logger.warning(f"<{self._service_id}> 处理请求前信号量为None，重新创建")
                self._semaphore = asyncio.Semaphore(self._max_concurrent)
            
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
                            self._logger.info(f"<{self._service_id}> Streaming response for {request.func_name}")
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
                    except zmq.ZMQError as e:
                        self._logger.error(f"<{self._service_id}> DEALER ZMQError: {e}")
                        await asyncio.sleep(2)
                    except Exception as e:
                        self._logger.error(f"<{self._service_id}> DEALER Handler error: {e}", exc_info=True)
                        await asyncio.sleep(2)
                except Exception as e:
                    self._logger.error(f"<{self._service_id}> DEALER Request processing error: {e}", exc_info=True)
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

    async def _heartbeat_loop(self):
        """心跳和健康监控循环"""
        counter = 0
        while self._state == DealerState.RUNNING:
            try:
                # 发送心跳
                if self._socket and self._state == DealerState.RUNNING:
                    await self._socket.send_multipart([b"heartbeat", b""])
                
                if not self._service_registered:
                    await self._register_to_router()

                # if counter % 100 == 19:
                #     self._socket.close()
                #     self._logger.info(f"<{self._service_id}> MOCK ERROR")                
            except asyncio.CancelledError:
                break
            except zmq.ZMQError as e:
                self._logger.error(f"<{self._service_id}> ZMQError in heartbeat loop: {e}")
                await self.request_reconnect()
                await asyncio.sleep(2)
            except Exception as e:
                self._logger.error(f"<{self._service_id}> Error in heartbeat loop: {e}")
                await self.request_reconnect()
                await asyncio.sleep(2)
            finally:
                counter = counter if counter < 100 else 0
                await asyncio.sleep(self._heartbeat_interval)

    async def request_reconnect(self):
        """请求重连"""
        self._heartbeat_status = False
        self._socket.close()
        self._socket = None
        self._service_registered = False
        self._process_messages_task.cancel()
        await asyncio.gather(self._process_messages_task, return_exceptions=True)

    async def _reconnect_monitor(self):
        """监控并处理重连请求"""        
        self._logger.info(f"<{self._service_id}> 重连监控器已启动")
        
        while self._state == DealerState.RUNNING:
            try:
                await asyncio.sleep(self._heartbeat_timeout)
                if self._reconnect_in_progress:
                    self._logger.info(f"<{self._service_id}> 重连中，跳过心跳检查")
                    continue
                
                not_living_interval = time.time() - self._last_successful_heartbeat

                # 检查心跳状态
                if self._heartbeat_status and not_living_interval > self._heartbeat_timeout:
                    self._reconnect_in_progress = True
                    self._logger.warning(f"<{self._service_id}> Heartbeat timeout detected")
                    await self.request_reconnect()
                    
                # 尝试重连
                if not self._heartbeat_status:
                    if await self._reconnect():
                        self._logger.info(f"<{self._service_id}> 重连成功 - 重置心跳状态")
                        # 确保心跳状态重置
                        self._last_successful_heartbeat = time.time()
                        self._heartbeat_status = True
                        self._reconnect_attempts = 0
                        self._process_messages_task = asyncio.create_task(self._process_messages(), name=f"{self._service_id}-process_messages")
                        await self._register_to_router()

                    else:
                        self._reconnect_attempts += 1
                        self._logger.warning(
                            f"<{self._service_id}> 重连失败 (尝试 {self._reconnect_attempts}/{self._max_reconnect_attempts})"
                        )
                        
                        # 多次失败后强制重连
                        if self._reconnect_attempts >= self._max_reconnect_attempts:
                            self._logger.warning(f"<{self._service_id}> 尝试深度重连")
                            await self._force_reconnect()
                            
                    self._reconnect_in_progress = False
                                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"<{self._service_id}> 重连监控器错误: {e}", exc_info=True)
                self._reconnect_in_progress = False

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
