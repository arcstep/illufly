from typing import Dict, Any, List, Optional, Union
import zmq
import zmq.asyncio
import asyncio
import logging
import json
import uuid
import time

from ..models import ReplyErrorBlock, RequestBlock, ReplyState, ReplyBlock
from .utils import serialize_message, deserialize_message

class ServiceRouter:
    """ZMQ ROUTER 实现，负责消息路由和服务发现"""
    def __init__(self, address: str, context: Optional[zmq.asyncio.Context] = None):
        self._context = context or zmq.asyncio.Context()
        self._address = address
        self._socket = self._context.socket(zmq.ROUTER)
        self._socket.set_hwm(1000)  # 设置高水位标记
        self._running = False
        self._services = {}
        self._service_heartbeats = {}
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
        self._services[service_id] = service_info
        self._logger.info(f"Registered service: {service_id}")

    def unregister_service(self, service_id: str):
        """注销服务"""
        if service_id in self._services:
            del self._services[service_id]
            self._logger.info(f"Unregistered service: {service_id}")

    async def _check_service_health(self):
        """检查服务健康状态"""
        while self._running:
            current_time = time.time()
            dead_services = []
            
            for service_id, last_time in self._service_heartbeats.items():
                if current_time - last_time > 30:  # 30秒无心跳视为服务死亡
                    dead_services.append(service_id)
            
            for service_id in dead_services:
                self.unregister_service(service_id)
                self._logger.warning(f"Service {service_id} died")
            
            await asyncio.sleep(10)

    async def _route_messages(self):
        """消息路由主循环"""
        self._logger.info("Router message loop started")
        while self._running:
            try:
                self._logger.info("Router waiting for messages...")
                multipart = await self._socket.recv_multipart()
                self._logger.info(f"Received message: {multipart}")
                
                sender_id = multipart[0]
                
                # 首先检查是否是来自服务的响应（3帧消息：[service_id, client_id, response]）
                try:
                    service_id = sender_id.decode()
                    if service_id in self._services and len(multipart) >= 3:
                        # 这是一个服务响应，直接转发给客户端
                        client_id = multipart[1]
                        response_frames = multipart[2:]
                        await self._socket.send_multipart([
                            client_id,
                            *response_frames
                        ])
                        self._logger.info(f"Forwarded response ({len(response_frames)} frames) from {service_id} to {client_id!r}")
                        continue
                except UnicodeDecodeError:
                    pass  # 不是服务ID，继续处理其他消息类型
                
                # 处理其他类型的消息
                message_type = multipart[1].decode()
                self._logger.info(f"Processing {message_type} from {sender_id!r}")
                
                if message_type == "ping":
                    await self._socket.send_multipart([
                        sender_id,
                        b"pong"
                    ])
                    
                elif message_type == "discovery":
                    # 返回所有已注册的服务信息
                    self._logger.info(f"Handling discovery request, services: {self._services}")
                    response = ReplyBlock(
                        request_id=str(uuid.uuid4()),
                        result=self._services,
                        state=ReplyState.SUCCESS
                    )
                    await self._socket.send_multipart([
                        sender_id,
                        serialize_message(response)
                    ])
                    self._logger.info("Discovery response sent")
                    
                elif message_type == "register":
                    service_id = sender_id.decode()
                    service_info = json.loads(multipart[2].decode())
                    self._services[service_id] = service_info
                    self._service_heartbeats[service_id] = time.time()
                    await self._socket.send_multipart([
                        sender_id,
                        b"ok"
                    ])
                    self._logger.info(f"Registered service {service_id} with methods: {list(service_info.keys())}")
                
                elif message_type == "heartbeat":
                    service_id = sender_id.decode()
                    if service_id in self._services:
                        self._service_heartbeats[service_id] = time.time()
                
                else:
                    # 处理服务调用
                    target_service_id = None
                    for service_id, methods in self._services.items():
                        if message_type in methods:
                            target_service_id = service_id
                            break
                    
                    if target_service_id:
                        await self._socket.send_multipart([
                            target_service_id.encode(),
                            sender_id,
                            multipart[2]
                        ])
                        self._logger.info(f"Forwarded {message_type} to {target_service_id}")
                    else:
                        error_msg = f"Method {message_type} not found in any service"
                        self._logger.error(error_msg)
                        error = ReplyErrorBlock(
                            request_id=str(uuid.uuid4()),
                            error=error_msg
                        )
                        await self._socket.send_multipart([
                            sender_id,
                            serialize_message(error)
                        ])
                    
            except Exception as e:
                self._logger.error(f"Router error: {e}", exc_info=True)

    async def _handle_discovery(self, sender_id: bytes):
        """处理服务发现请求"""
        await self._socket.send_multipart([
            sender_id,
            serialize_message(self._services)
        ])

    async def _handle_registration(self, sender_id: bytes, info_data: bytes):
        """处理服务注册请求"""
        try:
            service_info = json.loads(info_data.decode())
            service_id = sender_id.decode()
            self.register_service(service_id, service_info)
            self._service_heartbeats[service_id] = time.time()
            
            # 发送注册确认
            await self._socket.send_multipart([
                sender_id,
                b"register_ack",
                b""
            ])
        except Exception as e:
            self._logger.error(f"Registration error: {e}")

    async def _forward_request(self, sender_id: bytes, service_id: str, message: List[bytes]):
        """转发服务请求"""
        if service_id not in self._services:
            self._logger.warning(f"Service {service_id} not found")
            error = ReplyErrorBlock(
                request_id=str(uuid.uuid4()),
                error=f"Service {service_id} not found"
            )
            await self._socket.send_multipart([
                sender_id,
                serialize_message(error)
            ])
            return
        
        # 转发消息到服务处理器
        try:
            self._logger.info(f"Forwarding to {service_id}: {message}")
            await self._socket.send_multipart([
                service_id.encode(),  # 服务处理器ID
                sender_id,  # 原始发送者ID
                *message
            ])
        except zmq.Again:
            self._logger.warning("Message dropped due to HWM")