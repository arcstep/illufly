from typing import Dict, Optional, List
from .base import ServiceInfo, ServiceType, RegistryRequest, RegistryResponse
import zmq.asyncio  # 导入异步ZMQ
import logging
import time
import uuid
import asyncio

class RegistryClient:
    """注册中心客户端"""
    def __init__(self, mode: str = "inproc", host: str = "localhost", port: Optional[int] = None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.mode = mode
        self.context = zmq.asyncio.Context.instance()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.RCVTIMEO, 1000)
        self.socket.setsockopt(zmq.SNDTIMEO, 1000)
        
        # 根据模式构建地址
        if mode == "inproc":
            self.bus_address = "inproc://registry"
        elif mode == "tcp":
            self.bus_address = f"tcp://{host}:{port or 5555}"
        else:
            raise ValueError(f"不支持的通信模式: {mode}")
            
        self.socket.connect(self.bus_address)
        self.logger.info(f"正在连接到注册中心: {self.bus_address}")

    async def verify_connection(self):
        """异步验证与注册中心的连接"""
        try:
            request = RegistryRequest(
                action="ping",
                service="__verify__"
            )
            await self.socket.send_json(request.model_dump())
            
            # 使用 poll 来等待响应
            poller = zmq.asyncio.Poller()
            poller.register(self.socket, zmq.POLLIN)
            
            events = dict(await poller.poll(timeout=1000))  # 1秒超时
            
            if self.socket in events:
                response_data = await self.socket.recv_json()
                response = RegistryResponse.model_validate(response_data)
                
                if response.status != "success":
                    raise ConnectionError(f"连接验证失败: {response.message}")
                    
                self.logger.info("已成功连接到注册中心")
                return True
            else:
                raise TimeoutError("连接超时")
                
        except Exception as e:
            self.logger.error(f"连接验证失败: {e}")
            raise ConnectionError(f"无法连接到注册中心: {e}")

    def get_service_address(self, service_name: str) -> str:
        """根据当前模式生成服务地址"""
        if self.mode == "inproc":
            return f"inproc://{service_name}"
        elif self.mode == "tcp":
            return f"tcp://{self.host}:{self._get_next_port()}"
            
    def _get_next_port(self) -> int:
        """获取下一个可用端口（仅TCP模式使用）"""
        # 实现端口分配逻辑
        pass
        
    async def register_service(
        self,
        name: str,
        methods: Dict[str, str],
        service_type: ServiceType = ServiceType.REQUEST_REPLY,
        stream_address: Optional[str] = None
    ) -> RegistryResponse:
        """注册服务"""
        address = self.get_service_address(name)
        if service_type == ServiceType.STREAM and not stream_address:
            stream_address = self.get_service_address(f"{name}_stream")
            
        request = RegistryRequest(
            action="register",
            service=name,
            methods=methods,
            address=address,
            service_type=service_type,
            stream_address=stream_address
        )
        return await self._send_request(request)
        
    async def unregister_service(self, name: str) -> RegistryResponse:
        """注销服务"""
        request = RegistryRequest(
            action="unregister",
            service=name
        )
        return await self._send_request(request)
        
    async def discover_service(self, name: str) -> ServiceInfo:
        """发现服务"""
        request = RegistryRequest(
            action="discover",
            service=name
        )
        response = await self._send_request(request)
        if response.status != "success":
            raise ValueError(f"服务发现失败: {response.message}")
        return ServiceInfo.model_validate(response.data)
        
    async def list_services(self) -> List[ServiceInfo]:
        """列出所有服务"""
        request = RegistryRequest(
            action="list",
            service="*",
            methods=None,
            address=None
        )
        response = await self._send_request(request)
        if response.status != "success":
            raise ValueError(f"获取服务列表失败: {response.message}")
            
        # 确保 response.data 是列表
        if not isinstance(response.data, list):
            raise ValueError("服务列表数据格式错误")
            
        # 转换每个服务数据为 ServiceInfo 对象
        services = []
        for service_data in response.data:
            try:
                service_info = ServiceInfo.model_validate(service_data)
                services.append(service_info)
            except Exception as e:
                self.logger.error(f"解析服务信息失败: {e}")
                continue
                
        return services
        
    async def send_heartbeat(self, name: str) -> RegistryResponse:
        """发送服务心跳"""
        request = RegistryRequest(
            action="heartbeat",
            service=name
        )
        return await self._send_request(request)
        
    async def _send_request(self, request: RegistryRequest) -> RegistryResponse:
        """发送请求并接收响应"""
        try:
            self.logger.debug(f"发送请求: {request}")
            await self.socket.send_json(request.model_dump())  # 使用异步发送
            
            response_data = await self.socket.recv_json()  # 使用异步接收
            response = RegistryResponse.model_validate(response_data)
            self.logger.debug(f"收到响应: {response}")
            
            return response
            
        except zmq.error.Again:
            raise TimeoutError("请求超时")
        except Exception as e:
            self.logger.error(f"请求失败: {e}")
            raise
            
    async def close(self):  # 改为异步关闭
        """关闭客户端"""
        self.socket.close()
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        self.close() 