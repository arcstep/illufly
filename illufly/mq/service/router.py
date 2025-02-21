from typing import Dict, Any, List, Optional, Union, Set
from pydantic import BaseModel, Field
from enum import Enum
from time import time

import zmq
import zmq.asyncio
import asyncio
import logging
import json
import uuid

from ..models import ReplyErrorBlock, RequestBlock, ReplyState, ReplyBlock
from ..utils import serialize_message, deserialize_message

class ServiceState(str, Enum):
    """服务状态枚举"""
    ACTIVE = "active"       # 正常运行
    OVERLOAD = "overload"   # 接近满载，不再接受新请求
    INACTIVE = "inactive"   # 无响应/超时
    SHUTDOWN = "shutdown"   # 主动下线

class ServiceInfo(BaseModel):
    """服务信息模型"""
    service_id: str
    group: str = Field(default="default")
    methods: Dict[str, Any]
    state: ServiceState = ServiceState.ACTIVE
    max_concurrent: int = 100
    current_load: int = 0
    request_count: int = 0
    reply_count: int = 0
    last_heartbeat: float = Field(default_factory=time)

    @property
    def load_ratio(self) -> float:
        """负载率"""
        return self.current_load / self.max_concurrent

    def accept_request(self):
        """接受请求"""
        self.current_load += 1
        self.request_count += 1

    def complete_request(self):
        """完成请求"""
        self.current_load -= 1
        self.reply_count += 1

        if self.current_load < 0:
            self.current_load = 0

    def model_dump(self, **kwargs) -> dict:
        """自定义序列化方法"""
        data = super().model_dump(**kwargs)
        data['state'] = data['state'].value  # 将枚举转换为字符串
        return data

class ServiceRouter:
    """ZMQ ROUTER 实现，负责消息路由和服务发现"""
    def __init__(
        self, 
        address: str, 
        context: Optional[zmq.asyncio.Context] = None,
        heartbeat_interval: float = 10.0,    # 心跳检查间隔（秒）
        heartbeat_timeout: float = 30.0,     # 心跳超时时间（秒）
        request_timeout: float = 30.0,       # 请求超时时间（秒）
    ):
        self._context = context or zmq.asyncio.Context()
        self._address = address
        self._socket = self._context.socket(zmq.ROUTER)
        self._socket.set_hwm(1000)  # 设置高水位标记
        self._running = False
        self._services: Dict[str, ServiceInfo] = {}
        self._request_timeouts = {}  # 请求超时追踪
        
        # 可配置的超时参数
        self._HEARTBEAT_INTERVAL = heartbeat_interval
        self._HEARTBEAT_TIMEOUT = heartbeat_timeout
        self._REQUEST_TIMEOUT = request_timeout
        
        self._logger = logging.getLogger(__name__)

    async def start(self):
        """启动路由器"""
        if self._running:
            return
            
        try:
            # 先尝试绑定地址
            self._socket.bind(self._address)
            self._running = True
            self._message_task = asyncio.create_task(self._route_messages())
            self._health_check_task = asyncio.create_task(self._check_service_health())
            self._logger.info(f"Router started at {self._address}")
        except Exception as e:
            self._logger.error(f"Failed to start router: {e}")
            raise RuntimeError(f"Failed to start router: {e}") from e

    async def stop(self):
        """停止路由器"""
        if not self._running:
            return
            
        self._running = False
        if hasattr(self, '_message_task'):
            self._message_task.cancel()
        if hasattr(self, '_health_check_task'):
            self._health_check_task.cancel()
            
        try:
            self._socket.close()
            self._logger.info("Router stopped")
        except Exception as e:
            self._logger.error(f"Error stopping router: {e}")

    def register_service(self, service_id: str, service_info: Dict[str, Any]):
        """注册服务"""
        max_concurrent = service_info.get('max_concurrent', 100)  # 默认最大并发数
        methods = {f"{service_info.get('group', 'default')}.{name}": info for name, info in service_info.get('methods', {}).items()}
        self._services[service_id] = ServiceInfo(
            service_id=service_id,
            group=service_info.get('group', 'default'),
            methods=methods,
            max_concurrent=max_concurrent,
            current_load=service_info.get('current_load', 0),
            request_count=service_info.get('request_count', 0),
            reply_count=service_info.get('reply_count', 0)
        )
        self._logger.info(f"Registered service: {service_id} with max_concurrent={max_concurrent}: {methods}")

    def unregister_service(self, service_id: str):
        """注销服务"""
        if service_id in self._services:
            del self._services[service_id]
            self._logger.info(f"Unregistered service: {service_id}")

    async def _check_service_health(self):
        """检查服务健康状态"""
        while self._running:
            current_time = time()
            
            # 检查服务心跳
            for service_id, service in list(self._services.items()):
                if service.state != ServiceState.SHUTDOWN:  # 不检查已主动下线的服务
                    if current_time - service.last_heartbeat > self._HEARTBEAT_TIMEOUT:
                        if service.state != ServiceState.INACTIVE:
                            service.state = ServiceState.INACTIVE
                            # 服务变为不可用时记录日志
                            self._logger.warning(
                                f"Service {service_id} marked as inactive: "
                                f"last heartbeat was {current_time - service.last_heartbeat:.1f}s ago"
                            )
                            service.current_load = 0
            
            # 检查请求超时
            for request_id, (service_id, timestamp) in list(self._request_timeouts.items()):
                if current_time - timestamp > self._REQUEST_TIMEOUT:
                    if service_id in self._services:
                        service = self._services[service_id]
                        service.current_load -= 1
                        if service.current_load < 0:
                            service.current_load = 0
                        self._logger.warning(
                            f"Request {request_id} to service {service_id} timed out after "
                            f"{current_time - timestamp:.1f}s"
                        )
                    del self._request_timeouts[request_id]
            
            await asyncio.sleep(self._HEARTBEAT_INTERVAL)

    async def _send_error(self, sender_id: bytes, error: str):
        """发送错误消息"""
        error_response = ErrorBlock(
            request_id=str(uuid.uuid4()),
            error=error,
            state="error"
        )
        await self._socket.send_multipart([
            sender_id,
            b"error",
            serialize_message(error_response)
        ])
        self._logger.error(f"Error sending to {sender_id}: {error}")

    async def _route_messages(self):
        """消息路由主循环
        通信协议要求：
        1. identiy_id 必须为 UTF-8 编码的字符串
        2. 统一使用 multipart 格式
            - multipart[0] 为 identiy_id
            - multipart[1] 为消息类型
            - multipart[2:] 根据消息类型各自约定
        """
        while self._running:
            try:
                multipart = await self._socket.recv_multipart()
                sender_id_bytes = multipart[0]
                try:
                    sender_id = sender_id_bytes.decode()
                except UnicodeDecodeError:
                    await self._send_error(sender_id_bytes, "Invalid sender ID format: must be UTF-8 encoded string")
                    continue

                if len(multipart) < 2:
                    await self._send_error(sender_id_bytes, "Invalid message format: missing message type")
                    continue

                message_type = multipart[1].decode()
                self._logger.debug(
                    f"Router received message: type={message_type} from={sender_id}, {multipart}"
                )

                # 处理其他消息类型
                if message_type == "heartbeat":
                    if sender_id in self._services:
                        self._services[sender_id].last_heartbeat = time()
                        # 心跳消息不需要回复
                        
                elif message_type == "ping":
                    self._logger.debug(f"Handling ping from {sender_id}")
                    await self._socket.send_multipart([
                        sender_id_bytes,  # 发送给原始发送者
                        b"ping_ack",         # 消息类型
                        b"pong"          # 响应内容
                    ])
                
                elif message_type == "clusters":
                    # 收集所有可用的 DEALERS 节点信息
                    response = ReplyBlock(
                        request_id=str(uuid.uuid4()),
                        result={
                            k: v.model_dump() for k, v in self._services.items()
                        }
                    )
                    await self._socket.send_multipart([
                        sender_id_bytes,
                        b"clusters_ack",
                        serialize_message(response)
                    ])
                    
                elif message_type == "methods":
                    # 收集所有可用的方法信息
                    available_methods = {}
                    for service in self._services.values():
                        if service.state == ServiceState.ACTIVE:
                            for method_name, method_info in service.methods.items():
                                if method_name not in available_methods:
                                    available_methods[method_name] = method_info
                    
                    self._logger.info(f"Handling discovery request, available methods: {list(available_methods.keys())}")
                    response = ReplyBlock(
                        request_id=str(uuid.uuid4()),
                        result=available_methods
                    )
                    await self._socket.send_multipart([
                        sender_id_bytes,
                        b"methods_ack",
                        serialize_message(response)
                    ])
                    
                elif message_type == "register":
                    service_info = json.loads(multipart[2].decode())
                    self.register_service(sender_id, service_info)
                    router_config = {
                        "heartbeat_interval": self._HEARTBEAT_INTERVAL / 2,
                    }
                    await self._socket.send_multipart([
                        sender_id_bytes,
                        b"register_ack",
                        json.dumps(router_config).encode()
                    ])
                    
                elif message_type == "call":
                    if len(multipart) < 3:
                        self._logger.error("Invalid call message format")
                        continue
                        
                    service_name = multipart[2].decode()
                    
                    target_service = self._select_best_service(service_name)
                    if target_service and target_service.state == ServiceState.ACTIVE:
                        target_service.accept_request()
                        self._services[target_service.service_id].accept_request()
                        await self._socket.send_multipart([
                            target_service.service_id.encode(),
                            b"call",
                            sender_id_bytes,
                            *multipart[2:]
                        ])
                    else:
                        error_msg = f"No available service for method {method_name}"
                        self._logger.error(error_msg)
                        error = ReplyErrorBlock(
                            request_id=str(uuid.uuid4()),
                            error=error_msg
                        )
                        await self._socket.send_multipart([
                            sender_id_bytes,
                            b"reply",
                            serialize_message(error)
                        ])

                elif message_type in ["overload", "resume", "shutdown"]:
                    # 处理服务状态变更消息
                    if sender_id in self._services:
                        if message_type == "shutdown":
                            self._services[sender_id].state = ServiceState.SHUTDOWN
                            await self._socket.send_multipart([
                                sender_id_bytes,
                                b"shutdown_ack",
                            ])
                        elif message_type == "overload":
                            # 不必回复
                            self._services[sender_id].state = ServiceState.OVERLOAD
                        elif message_type == "resume":
                            # 不必回复
                            self._services[sender_id].state = ServiceState.ACTIVE

                # 如果是已注册服务的回复消息，直接转发给客户端
                elif sender_id in self._services and message_type == "reply":
                    if len(multipart) < 3:
                        await self._send_error(sender_id_bytes, "Invalid reply format")
                        continue
                        
                    target_client_id = multipart[2]  # 目标客户端ID
                    response_data = multipart[3] if len(multipart) > 3 else b""
                    
                    # 直接转发响应给客户端
                    await self._socket.send_multipart([
                        target_client_id,
                        b"reply",
                        response_data
                    ])
                    self._services[sender_id].complete_request()

                else:
                    await self._send_error(sender_id_bytes, f"Unknown message type: {message_type}")

            except Exception as e:
                self._logger.error(f"Router error: {e}", exc_info=True)
                await self._send_error(sender_id_bytes, f"Service Router Error")

    def _select_best_service(self, method_name: str) -> Optional[ServiceInfo]:
        """选择最佳服务实例"""
        available_services = [
            service for service in self._services.values()
            if (method_name in service.methods and 
                service.state == ServiceState.ACTIVE and
                service.current_load < service.max_concurrent)
        ]
        for service in available_services:
            s = self._services[service.service_id]
            self._logger.info(f"Available service for [{method_name}]: {s.service_id} current_load: {s.current_load} / max_concurrent: {s.max_concurrent}")
        
        if not available_services:
            return None
            
        # 选择负载最小的服务
        return min(available_services, key=lambda s: s.current_load)