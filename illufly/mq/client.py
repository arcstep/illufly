from typing import Any, AsyncIterator, Dict, Union, Optional, AsyncGenerator
from enum import Enum
import zmq.asyncio
import json
import logging
from .base import MQBus
from .types import (
    ServiceInfo,
    ServiceMode,
    ServiceRequest,
    ServiceResponse
)
from .registry import RegistryClient
import uuid
import asyncio

class MQClient:
    """消息队列客户端"""
    def __init__(self, registry_client: RegistryClient):
        self.registry_client = registry_client
        self.context = zmq.asyncio.Context.instance()
        self.sockets = {}
        self.logger = logging.getLogger(__name__)

    def discover_service(self, service_name: str) -> ServiceInfo:
        """发现服务"""
        return self.registry_client.discover_service(service_name)

    async def call(self, service_name: str, method: str, params: dict = None) -> Any:
        """调用服务方法（用于 REQUEST_REPLY 和 ROUTER 模式）"""
        service_info = await self.discover_service(service_name)
        socket = await self._get_socket(service_info)
        
        if service_info.service_mode not in (ServiceMode.REQUEST_REPLY, ServiceMode.ROUTER):
            raise ValueError(f"服务 {service_name} 不支持 call 方法，请使用对应的模式方法")
            
        request = {
            "method": method,
            "params": params or {}
        }
        
        if service_info.service_mode == ServiceMode.ROUTER:
            return StreamResponseIterator(socket, request)
        else:
            await socket.send_json(request)
            return await socket.recv_json()
            
    async def push(self, service_name: str, data: dict) -> None:
        """推送数据（用于 PUSH_PULL 模式）"""
        service_info = await self.discover_service(service_name)
        if service_info.service_mode != ServiceMode.PUSH_PULL:
            raise ValueError(f"服务 {service_name} 不是 PUSH_PULL 模式")
            
        socket = await self._get_socket(service_info)
        await socket.send_json(data)
        
    async def subscribe(self, service_name: str, topic: str = "") -> AsyncGenerator:
        """订阅数据（用于 PUB_SUB 模式）"""
        service_info = await self.discover_service(service_name)
        if service_info.service_mode != ServiceMode.PUB_SUB:
            raise ValueError(f"服务 {service_name} 不是 PUB_SUB 模式")
            
        socket = await self._get_socket(service_info)
        socket.setsockopt_string(zmq.SUBSCRIBE, topic)
        
        while True:
            try:
                [topic, msg] = await socket.recv_multipart()
                yield json.loads(msg)
            except Exception as e:
                self.logger.error(f"接收订阅消息时出错: {e}")
                break
                
    async def pipeline(self, service: str, data: Dict) -> Dict:
        """管道模式调用"""
        # 需要修改客户端实现
        service_info = await self.discover_service(service)
        socket = self.context.socket(zmq.PUSH)  # 使用 PUSH socket
        try:
            socket.connect(service_info.address)
            # 连接响应地址
            response_socket = self.context.socket(zmq.PULL)
            response_address = f"inproc://{service}_response"
            response_socket.connect(response_address)
            
            # 发送请求
            await socket.send_multipart([json.dumps(data).encode()])
            # 等待响应
            response = await response_socket.recv_multipart()
            return json.loads(response[0].decode())
        finally:
            socket.close()
            response_socket.close()
        
    async def _get_socket(self, service_info, suffix=""):
        """获取或创建套接字"""
        socket_key = f"{service_info.name}{suffix}"
        
        if socket_key not in self.sockets:
            socket_type = {
                ServiceMode.REQUEST_REPLY: zmq.REQ,
                ServiceMode.PUSH_PULL: zmq.PUSH,
                ServiceMode.PUB_SUB: zmq.SUB,
                ServiceMode.ROUTER: zmq.DEALER,
                ServiceMode.PIPELINE: zmq.PULL if suffix == "_output" else zmq.PUSH
            }[service_info.service_mode]
            
            socket = self.context.socket(socket_type)
            socket.connect(service_info.address)
            self.sockets[socket_key] = socket
            
        return self.sockets[socket_key]
        
    async def close(self):
        """关闭所有套接字"""
        for socket in self.sockets.values():
            socket.close()
        self.sockets.clear() 
        
class StreamResponseIterator:
    """异步迭代器类，用于处理流式响应"""
    def __init__(self, socket, request):
        self.socket = socket
        self.request = request
        self._started = False
        
    def __aiter__(self):
        return self
        
    async def __anext__(self):
        if not self._started:
            await self.socket.send_multipart([b"", json.dumps(self.request).encode()])
            self._started = True
            
        try:
            _, response = await self.socket.recv_multipart()
            data = json.loads(response)
            
            if isinstance(data, dict) and data.get("__end__"):
                raise StopAsyncIteration
                
            return data
        except Exception as e:
            if not isinstance(e, StopAsyncIteration):
                logging.error(f"接收流响应时出错: {e}")
            raise StopAsyncIteration 