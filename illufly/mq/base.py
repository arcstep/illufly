import zmq
import json
import logging
from typing import Dict, Any, Optional, Callable, List
from pydantic import BaseModel, Field
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from ..envir import get_env
import threading
import time

class ServiceStatus(str, Enum):
    """服务状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"

class ServiceInfo(BaseModel):
    """服务信息模型"""
    name: str = Field(..., description="服务名称")
    methods: Dict[str, str] = Field(default_factory=dict, description="服务方法映射")
    address: str = Field(..., description="服务地址")
    status: ServiceStatus = Field(default=ServiceStatus.ACTIVE, description="服务状态")
    last_heartbeat: float = Field(default_factory=time.time)

class RegistryRequest(BaseModel):
    """注册请求模型"""
    action: str = Field(..., description="操作类型")
    service: str = Field(..., description="服务名称")
    methods: Optional[Dict[str, str]] = Field(default=None, description="服务方法")
    address: Optional[str] = Field(default=None, description="服务地址")

class RegistryResponse(BaseModel):
    """注册响应模型"""
    status: str = Field(..., description="响应状态")
    message: str = Field(..., description="响应消息")
    data: Optional[Dict[str, Any]] = Field(default=None, description="响应数据")

class MQBus:
    """MQ总线管理类"""
    MODE_TCP = "tcp"
    MODE_INPROC = "inproc"
    
    INPROC_FRONTEND = "inproc://frontend"
    INPROC_BACKEND = "inproc://backend"
    INPROC_REGISTRY = "inproc://registry"
    
    def __init__(self, mode: Optional[str] = None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self.context = zmq.Context.instance()  # 使用单例模式
        
        # 使用环境变量或默认值
        self.mode = mode or get_env("ILLUFLY_MQ_MODE")
        self.registry_port = get_env("ILLUFLY_MQ_REGISTRY_PORT")
        
        # 根据模式选择连接地址
        registry_addr = (self.INPROC_REGISTRY if self.mode == self.MODE_INPROC 
                        else f"tcp://*:{self.registry_port}")
        
        self.logger.info(f"初始化注册中心套接字: {registry_addr}")
        
        # 初始化注册中心套接字
        self._init_registry(registry_addr)
        
        self.services: Dict[str, ServiceInfo] = {}
        self.running = False
        self.logger.info("MQ总线初始化完成")

    def _init_registry(self, addr: str):
        """初始化注册中心套接字"""
        self.registry = self.context.socket(zmq.REP)
        # 设置套接字选项
        self.registry.setsockopt(zmq.LINGER, 0)  # 关闭时立即释放
        self.registry.setsockopt(zmq.RCVTIMEO, 1000)  # 接收超时1秒
        self.registry.setsockopt(zmq.SNDTIMEO, 1000)  # 发送超时1秒
        self.registry.bind(addr)

    def start(self):
        """启动MQ总线"""
        if self.running:
            return
        
        self.running = True
        self.worker_thread = threading.Thread(
            target=self._registry_worker,
            name="RegistryWorker",
            daemon=True
        )
        self.worker_thread.start()
        self.logger.info("MQ总线启动完成")

    def stop(self):
        """停止MQ总线"""
        if not self.running:
            return
            
        self.logger.info("正在停止MQ总线...")
        self.running = False
        
        if hasattr(self, 'worker_thread'):
            self.worker_thread.join(timeout=1.0)
        
        self.registry.close()
        self.logger.info("MQ总线已停止")

    def _registry_worker(self):
        """注册中心工作线程"""
        self.logger.info("注册中心工作线程开始运行")
        
        while self.running:
            try:
                self.logger.info("等待接收请求...")
                try:
                    message = self.registry.recv_json()
                    self.logger.info(f"成功接收到请求: {message}")
                except zmq.error.Again:
                    self.logger.debug("接收超时，继续等待...")  # 使用debug级别避免日志过多
                    continue
                except Exception as e:
                    self.logger.error(f"接收消息出错: {e}")
                    continue

                try:
                    request = RegistryRequest.model_validate(message)
                    self.logger.info(f"处理请求: {request}")
                    response = self._handle_request(request)
                    self.logger.info(f"准备发送响应: {response}")
                    
                    self.registry.send_json(response.model_dump())
                    self.logger.info("响应发送成功")
                    
                except zmq.error.Again:
                    self.logger.error("发送响应超时")
                except Exception as e:
                    self.logger.error(f"处理请求出错: {e}")
                    try:
                        error_response = RegistryResponse(
                            status='error',
                            message=str(e)
                        )
                        self.registry.send_json(error_response.model_dump())
                    except:
                        self.logger.error("发送错误响应失败")
                    
            except Exception as e:
                self.logger.error(f"工作线程出错: {e}")

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
        
        if request.action == "register":
            # 注册服务
            self.services[request.service] = ServiceInfo(
                name=request.service,
                methods=request.methods or {},
                address=request.address,
                last_heartbeat=time.time()
            )
            return RegistryResponse(
                status="success",
                message=f"服务 {request.service} 注册成功"
            )
        
        elif request.action == "unregister":
            # 注销服务
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
            # 发现服务
            if request.service in self.services:
                service_info = self.services[request.service]
                return RegistryResponse(
                    status="success",
                    message=f"发现服务 {request.service}",
                    data=service_info.model_dump()
                )
            return RegistryResponse(
                status="error",
                message=f"服务 {request.service} 不存在"
            )
        
        elif request.action == "heartbeat":
            # 心跳更新
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
        
        return RegistryResponse(
            status="error",
            message=f"未知的操作类型: {request.action}"
        )
