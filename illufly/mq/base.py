import zmq.asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable, List, Union
from pydantic import BaseModel, Field
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from ..envir import get_env
import threading
import time
import asyncio
from threading import Thread

class ServiceStatus(str, Enum):
    """服务状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"

class ServiceType(str, Enum):
    REQUEST_REPLY = "request_reply"
    STREAM = "stream"

class ServiceInfo(BaseModel):
    """服务信息模型"""
    name: str
    methods: Dict[str, str]
    address: str
    status: ServiceStatus = ServiceStatus.ACTIVE
    service_type: ServiceType = ServiceType.REQUEST_REPLY
    stream_address: Optional[str] = None
    last_heartbeat: float = Field(default_factory=time.time)

class RegistryRequest(BaseModel):
    """注册请求模型"""
    action: str
    service: str
    methods: Optional[Dict[str, str]] = None
    address: Optional[str] = None
    service_type: ServiceType = ServiceType.REQUEST_REPLY
    stream_address: Optional[str] = None

class RegistryResponse(BaseModel):
    """注册响应模型"""
    status: str
    message: str
    data: Optional[Union[Dict, List[Dict]]] = None  # 允许字典或字典列表

class MQBus:
    """MQ总线管理类"""
    MODE_TCP = "tcp"
    MODE_INPROC = "inproc"
    
    INPROC_FRONTEND = "inproc://frontend"
    INPROC_BACKEND = "inproc://backend"
    INPROC_REGISTRY = "inproc://registry"
    
    def __init__(self, mode: Optional[str] = None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.context = zmq.asyncio.Context.instance()  # 使用异步Context
        
        # 使用环境变量或默认值
        self.mode = mode or get_env("ILLUFLY_MQ_MODE")
        self.registry_port = get_env("ILLUFLY_MQ_REGISTRY_PORT")
        
        # 根据模式选择连接地址
        registry_addr = (self.INPROC_REGISTRY if self.mode == self.MODE_INPROC 
                        else f"tcp://*:{self.registry_port}")
        
        self.logger.info(f"初始化注册中心套接字: {registry_addr}")
        
        # 初始化注册中心套接字
        self._init_registry(registry_addr)
        
        # 新增流服务代理
        self.stream_proxy = self.context.socket(zmq.XPUB)
        
        self.services: Dict[str, ServiceInfo] = {}
        self.running = False
        self.worker_task = None  # 用于存储异步任务
        self.loop = None  # 用于存储事件循环
        self.logger.info("MQ总线初始化完成")

    def _init_registry(self, addr: str):
        """初始化注册中心套接字"""
        self.registry = self.context.socket(zmq.REP)
        # 设置套接字选项
        self.registry.setsockopt(zmq.LINGER, 0)  # 关闭时立即释放
        self.registry.setsockopt(zmq.RCVTIMEO, 1000)  # 接收超时1秒
        self.registry.setsockopt(zmq.SNDTIMEO, 1000)  # 发送超时1秒
        self.registry.bind(addr)

    def _init_stream_proxy(self, addr: str):
        """初始化流服务代理"""
        self.stream_proxy.bind(addr)
        # 设置代理选项
        self.stream_proxy.setsockopt(zmq.XPUB_VERBOSE, 1)

    def start(self):
        """启动MQ总线"""
        self.logger.info("正在启动MQ总线...")
        self.running = True
        
        # 创建新的事件循环
        self.loop = asyncio.new_event_loop()
        
        # 在新线程中运行事件循环
        def run_event_loop():
            asyncio.set_event_loop(self.loop)
            self.worker_task = self.loop.create_task(self._registry_worker())
            self.loop.run_forever()
            
        self.thread = Thread(target=run_event_loop, daemon=True)
        self.thread.start()
        
        self.logger.info("MQ总线启动完成")

    def stop(self):
        """停止MQ总线"""
        self.logger.info("正在停止MQ总线...")
        self.running = False
        
        if self.loop:
            try:
                # 创建一个Future来等待任务完成
                async def cleanup():
                    if self.worker_task and not self.worker_task.done():
                        self.worker_task.cancel()
                        try:
                            await self.worker_task
                        except asyncio.CancelledError:
                            pass
                
                # 在事件循环中执行清理
                future = asyncio.run_coroutine_threadsafe(cleanup(), self.loop)
                future.result(timeout=5)  # 设置超时时间
                
                # 停止事件循环
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.thread.join(timeout=5)  # 设置超时时间
                
                # 关闭事件循环
                if not self.loop.is_closed():
                    self.loop.close()
                
            except Exception as e:
                self.logger.error(f"停止MQ总线时出错: {e}")
            finally:
                self.loop = None
                self.worker_task = None
                
                # 确保socket被关闭
                try:
                    self.registry.close(linger=0)
                except Exception as e:
                    self.logger.error(f"关闭socket时出错: {e}")
        
        self.logger.info("MQ总线已停止")

    async def _registry_worker(self):
        """异步注册中心工作线程"""
        self.logger.info("注册中心工作线程开始运行")
        
        while self.running:
            try:
                self.logger.info("等待接收请求...")
                try:
                    message = await self.registry.recv_json()
                    self.logger.info(f"成功接收到请求: {message}")
                    
                    request = RegistryRequest.model_validate(message)
                    self.logger.info(f"处理请求: {request}")
                    
                    response = self._handle_request(request)
                    self.logger.info(f"准备发送响应: {response}")
                    
                    # 确保响应被发送
                    await self.registry.send_json(response.model_dump())
                    self.logger.info("响应发送成功")
                    
                except zmq.error.Again:
                    # 只记录调试信息，避免日志过多
                    self.logger.debug("等待新请求...")
                    await asyncio.sleep(0.1)  # 添加短暂延迟
                    continue
                    
            except asyncio.CancelledError:
                self.logger.info("工作线程被取消")
                break
            except Exception as e:
                self.logger.error(f"处理请求出错: {e}")
                try:
                    # 尝试发送错误响应
                    error_response = RegistryResponse(
                        status="error",
                        message=str(e)
                    )
                    await self.registry.send_json(error_response.model_dump())
                except Exception as send_error:
                    self.logger.error(f"发送错误响应失败: {send_error}")

    def _handle_register(self, request: RegistryRequest) -> RegistryResponse:
        """处理服务注册请求"""
        try:
            service_info = ServiceInfo(
                name=request.service,
                methods=request.methods or {},
                address=request.address or '',
                status=ServiceStatus.ACTIVE
            )
            self.services[request.service] = service_info
            self.logger.info(f"服务注册成功: {request.service}")
            return RegistryResponse(
                status='success',
                message=f'服务 {request.service} 注册成功'
            )
        except Exception as e:
            return RegistryResponse(
                status='error',
                message=f'注册信息不完整: {str(e)}'
            )

    def _handle_unregister(self, request: RegistryRequest) -> RegistryResponse:
        """处理服务注销请求"""
        if request.service in self.services:
            del self.services[request.service]
            self.logger.info(f"服务注销成功: {request.service}")
            return RegistryResponse(
                status='success',
                message=f'服务 {request.service} 注销成功'
            )
        return RegistryResponse(
            status='error',
            message=f'服务 {request.service} 不存在'
        )

    def _handle_discover(self, request: RegistryRequest) -> RegistryResponse:
        """处理服务发现请求"""
        if request.service:
            service = self.services.get(request.service)
            if service:
                return RegistryResponse(
                    status='success',
                    message='服务发现成功',
                    data={'service': service.model_dump()}
                )
            return RegistryResponse(
                status='error',
                message=f'服务 {request.service} 不存在'
            )
        
        # 返回所有活跃服务
        active_services = {
            name: svc.model_dump()
            for name, svc in self.services.items()
            if svc.status == ServiceStatus.ACTIVE
        }
        return RegistryResponse(
            status='success',
            message='获取所有活跃服务成功',
            data={'services': active_services}
        )

    def _handle_heartbeat(self, request: RegistryRequest) -> RegistryResponse:
        """处理服务心跳请求"""
        if request.service in self.services:
            self.services[request.service].status = ServiceStatus.ACTIVE
            return RegistryResponse(
                status='success',
                message='heartbeat received'
            )
        return RegistryResponse(
            status='error',
            message=f'服务 {request.service} 不存在'
        )

    def get_service_info(self, service_name: str) -> Optional[ServiceInfo]:
        """获取服务信息"""
        return self.services.get(service_name)

    def list_services(self) -> Dict[str, ServiceInfo]:
        """列出所有活跃服务"""
        return {
            name: svc 
            for name, svc in self.services.items() 
            if svc.status == ServiceStatus.ACTIVE
        }

    def _handle_request(self, request: RegistryRequest) -> RegistryResponse:
        """处理注册中心请求"""
        self.logger.info(f"处理{request.action}请求: {request}")
        
        try:
            if request.action == "ping":
                return RegistryResponse(
                    status="success",
                    message="pong"
                )
                
            elif request.action == "register":
                # 验证地址格式是否与总线模式匹配
                if self.mode == MQBus.MODE_INPROC and not request.address.startswith("inproc://"):
                    return RegistryResponse(
                        status="error",
                        message=f"地址格式错误: 当前模式为inproc，但地址为 {request.address}"
                    )
                
                # 注册服务
                self.services[request.service] = ServiceInfo(
                    name=request.service,
                    methods=request.methods or {},
                    address=request.address,
                    service_type=request.service_type,
                    stream_address=request.stream_address,
                    last_heartbeat=time.time()
                )
                self.logger.info(f"服务注册成功: {request.service}")
                return RegistryResponse(
                    status="success",
                    message=f"服务 {request.service} 注册成功"
                )
                
            elif request.action == "unregister":
                if request.service in self.services:
                    del self.services[request.service]
                    return RegistryResponse(
                        status="success",
                        message=f"服务 {request.service} 注销成功"
                    )
                return RegistryResponse(
                    status="error",
                    message=f"服务 {request.service} 不存在"
                )
                
            elif request.action == "discover":
                if request.service in self.services:
                    return RegistryResponse(
                        status="success",
                        message=f"服务 {request.service} 发现成功",
                        data=self.services[request.service].model_dump()
                    )
                return RegistryResponse(
                    status="error",
                    message=f"服务 {request.service} 不存在"
                )
                
            elif request.action == "list":
                return RegistryResponse(
                    status="success",
                    message="获取服务列表成功",
                    data=[service.model_dump() for service in self.services.values()]
                )
                
            elif request.action == "heartbeat":
                if request.service in self.services:
                    self.services[request.service].last_heartbeat = time.time()
                    return RegistryResponse(
                        status="success",
                        message=f"服务 {request.service} 心跳更新成功"
                    )
                return RegistryResponse(
                    status="error",
                    message=f"服务 {request.service} 不存在"
                )
                
            else:
                return RegistryResponse(
                    status="error",
                    message=f"未知的操作类型: {request.action}"
                )
                
        except Exception as e:
            self.logger.error(f"处理请求出错: {e}")
            return RegistryResponse(
                status="error",
                message=f"处理请求出错: {str(e)}"
            )
