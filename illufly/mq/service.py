import zmq.asyncio
import logging
import json
from typing import Dict, Any, AsyncGenerator, Union, Optional, Generator
from .types import ServiceMode
from .registry import RegistryClient
import asyncio
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import threading
import time
import multiprocessing

class ConcurrencyMode(str, Enum):
    """并发模式"""
    ASYNC = 'async'          # 纯异步模式
    THREAD = 'thread'        # 单独线程模式
    THREADPOOL = 'threadpool'  # 线程池模式

class BaseService():
    """服务基类"""
    def __init__(
        self, 
        name: str, 
        registry_client: RegistryClient,
        service_mode: ServiceMode,
        concurrency_mode: ConcurrencyMode = ConcurrencyMode.ASYNC,
        max_workers: int = None,
        logger=None
    ):
        self.name = name
        self.registry_client = registry_client
        self.service_mode = service_mode
        self.concurrency_mode = concurrency_mode
        self.max_workers = max_workers or multiprocessing.cpu_count()
        self.logger = logger or logging.getLogger(__name__)
        
        # ZMQ上下文
        if concurrency_mode == ConcurrencyMode.ASYNC:
            self.context = zmq.asyncio.Context.instance()
        else:
            self.context = zmq.Context.instance()
            
        self.socket = None
        self.address = self.registry_client.get_service_address(name)
        self._running = False
        self._process_task = None
        self._thread = None
        self._thread_pool = None
        
        # 对于管道模式，需要输入和输出地址
        if service_mode == ServiceMode.PIPELINE:
            self.input_address = f"{self.address}_in"
            self.output_address = f"{self.address}_out"
            self.input_socket = None
            self.output_socket = None
            
        self.logger.info(f"初始化服务 {name}, 模式: {service_mode}")
        
    async def start(self):
        """启动服务"""
        if self._running:
            return
            
        self.logger.info(f"正在启动服务 {self.name}...")
        
        try:
            # 初始化并发处理器
            if self.concurrency_mode == ConcurrencyMode.THREADPOOL:
                self._thread_pool = ThreadPoolExecutor(
                    max_workers=self.max_workers,
                    thread_name_prefix=f"{self.name}_worker"
                )
                
            # 初始化钩子
            await self.on_init()
            
            # 设置套接字
            await self._setup_socket()
            
            # 注册服务
            await self.registry_client.register_service(
                name=self.name,
                methods=await self.get_methods(),
                service_mode=self.service_mode,
                stream_address=self.response_address if self.service_mode == ServiceMode.PIPELINE else None
            )
            
            # 启动钩子
            await self.on_start()
            
            # 根据并发模式启动处理循环
            self._running = True
            if self.concurrency_mode == ConcurrencyMode.ASYNC:
                self._process_task = asyncio.create_task(
                    self._process_requests_async(),
                    name=f"{self.name}_process"
                )
            elif self.concurrency_mode == ConcurrencyMode.THREAD:
                self._thread = threading.Thread(
                    target=self._process_requests_thread,
                    name=f"{self.name}_process"
                )
                self._thread.start()
            else:  # THREADPOOL
                self._process_task = asyncio.create_task(
                    self._process_requests_pool(),
                    name=f"{self.name}_process"
                )
                
        except Exception as e:
            self.logger.error(f"服务启动失败: {e}")
            await self.stop()
            raise
            
    async def stop(self):
        """停止服务"""
        if not self._running:
            return
            
        self.logger.info(f"正在停止服务 {self.name}...")
        self._running = False
        
        try:
            # 停止处理循环
            if self._process_task:
                self._process_task.cancel()
                try:
                    await self._process_task
                except asyncio.CancelledError:
                    pass
                self._process_task = None
                
            if self._thread:
                self._thread.join()
                self._thread = None
                
            if self._thread_pool:
                self._thread_pool.shutdown(wait=True)
                self._thread_pool = None
                
            # 停止钩子
            await self.on_stop()
            
            # 注销服务
            await self.registry_client.unregister_service(name=self.name)
            
            # 关闭套接字
            if self.socket:
                self.socket.close()
                self.socket = None
                
        except Exception as e:
            self.logger.error(f"服务停止时出错: {e}")
            raise
            
    async def _setup_socket(self):
        """设置套接字"""
        if self.service_mode == ServiceMode.PIPELINE:
            # PIPELINE 模式使用 PULL socket 接收数据
            socket_type = zmq.PULL
            self.logger.info(f"创建 PIPELINE 模式 socket: PULL")
            self.socket = self.context.socket(socket_type)
            self.socket.setsockopt(zmq.LINGER, 0)
            
            # 创建响应 socket
            response_address = f"inproc://{self.name}_response"
            self.response_socket = self.context.socket(zmq.PUSH)
            self.response_socket.setsockopt(zmq.LINGER, 0)
            self.response_socket.bind(response_address)
            self.logger.info(f"创建响应 socket: PUSH, 地址: {response_address}")
            
            # 保存响应地址供客户端使用
            self.response_address = response_address
        else:
            socket_type = {
                ServiceMode.REQUEST_REPLY: zmq.REP,
                ServiceMode.PUSH_PULL: zmq.PULL,  # 服务端应该是 PULL 端
                ServiceMode.PUB_SUB: zmq.PUB,
                ServiceMode.ROUTER: zmq.ROUTER,
                ServiceMode.PIPELINE: zmq.DEALER
            }[self.service_mode]
            
            self.socket = self.context.socket(socket_type)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.bind(self.address)
            
            # 对于管道模式，需要输入和输出套接字
            if self.service_mode == ServiceMode.PIPELINE:
                self.input_socket = self.context.socket(zmq.PULL)
                self.output_socket = self.context.socket(zmq.PUSH)
                self.input_socket.bind(self.input_address)
                self.output_socket.bind(self.output_address)
                
                self.logger.info(f"创建 PIPELINE 模式 socket: DEALER")
        
    # 不同并发模式的处理循环实现
    async def _process_requests_async(self):
        """异步模式的处理循环"""
        self.logger.info(f"服务 {self.name} 开始处理请求 (异步模式)...")
        while self._running:
            try:
                if not await self._process_one_request():
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"处理请求时出错: {e}")
                await asyncio.sleep(0.5)
                await self.handle_error(e)
                
    def _process_requests_thread(self):
        """线程模式的处理循环"""
        self.logger.info(f"服务 {self.name} 开始处理请求 (线程模式)...")
        while self._running:
            try:
                if not self._process_one_request_sync():
                    time.sleep(0.01)
            except Exception as e:
                self.logger.error(f"处理请求时出错: {e}")
                time.sleep(0.5)
                asyncio.run(self.handle_error(e))
                
    async def _process_requests_pool(self):
        """线程池模式的处理循环"""
        self.logger.info(f"服务 {self.name} 开始处理请求 (线程池模式)...")
        while self._running:
            try:
                request = await self._receive_request()
                if request:
                    # 在线程池中处理请求
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        self._thread_pool,
                        partial(self._process_request_sync, request)
                    )
                else:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"处理请求时出错: {e}")
                await asyncio.sleep(0.5)
                await self.handle_error(e)
        
    async def _process_one_request(self) -> bool:
        """处理单个请求"""
        try:
            self.logger.debug(f"处理请求 (模式: {self.service_mode})")
            # 优先使用 process_message 方法
            if hasattr(self, 'process_message') and self.process_message.__func__ is not BaseService.process_message:
                message = await self._receive_message()
                result = await self.process_message(message)
                await self._handle_result(result)
                return True
                
            # 否则使用专用方法
            if self.service_mode in (ServiceMode.REQUEST_REPLY, ServiceMode.ROUTER):
                return await self._handle_request()
            elif self.service_mode == ServiceMode.PIPELINE:
                return await self._handle_pipeline()
            elif self.service_mode == ServiceMode.PUB_SUB:
                return await self._handle_publication()
            elif self.service_mode == ServiceMode.PUSH_PULL:
                return await self._handle_push_pull()
                
        except zmq.Again:
            return False
            
        except Exception as e:
            self.logger.error(f"处理请求失败: {e}", exc_info=True)
            await self.handle_error(e)
            return False
        
    async def _handle_request(self) -> bool:
        """处理 REQUEST_REPLY 和 ROUTER 模式"""
        try:
            if self.service_mode == ServiceMode.ROUTER:
                identity, empty, request = await self.socket.recv_multipart(flags=zmq.NOBLOCK)
                result_gen = self.process_request(json.loads(request))
                # 检查返回类型
                if isinstance(result_gen, (AsyncGenerator, Generator)):
                    async for item in result_gen:
                        await self._handle_result(item, identity)
                    # 发送结束标记
                    await self._handle_result({"__end__": True}, identity)
                else:
                    # 处理普通返回值
                    await self._handle_result(result_gen, identity)
                return True
            else:
                request = await self.socket.recv_json(flags=zmq.NOBLOCK)
                result = await self.process_request(request)
                await self._handle_result(result)
                return True
                
        except zmq.Again:
            return False
        
    async def _handle_pipeline(self) -> bool:
        """处理 PIPELINE 模式"""
        try:
            message = await self.socket.recv_multipart(flags=zmq.NOBLOCK)
            if message:
                self.logger.debug(f"收到 PIPELINE 消息: {message}")
                data = json.loads(message[0])
                result = await self.process_pipeline(data)
                
                if result is not None:
                    self.logger.debug(f"发送处理结果: {result}")
                    await self.response_socket.send_multipart([
                        json.dumps(result).encode()
                    ])
                return True
            return False
        except zmq.Again:
            return False
        except Exception as e:
            self.logger.error(f"PIPELINE处理错误: {e}", exc_info=True)
            raise
        
    async def _handle_publication(self) -> bool:
        """处理 PUB_SUB 模式"""
        async for topic, data in self.generate_publication():
            await self.socket.send_multipart([
                topic.encode(),
                json.dumps(data).encode()
            ])
        return True
        
    async def _handle_push_pull(self) -> bool:
        """处理 PUSH_PULL 模式"""
        data = await self.socket.recv_json(flags=zmq.NOBLOCK)
        await self.process_request(data)  # 忽略返回值
        return True
        
    async def _handle_result(self, result: Any, identity: bytes = None):
        """统一处理返回结果"""
        try:
            if self.service_mode == ServiceMode.ROUTER:
                if isinstance(result, (AsyncGenerator, Generator)):
                    async for item in result:
                        await self.socket.send_multipart([
                            identity,
                            b"",
                            json.dumps(item).encode()
                        ])
                    # 发送结束标记
                    await self.socket.send_multipart([
                        identity,
                        b"",
                        json.dumps({"__end__": True}).encode()
                    ])
                else:
                    await self.socket.send_multipart([
                        identity,
                        b"",
                        json.dumps(result).encode()
                    ])
                    
            elif self.service_mode in (ServiceMode.REQUEST_REPLY, ServiceMode.PIPELINE):
                await self.socket.send_json(result)
                
            # PUSH_PULL 模式不需要发送响应
            # PUB_SUB 模式在 _handle_publication 中处理
            
        except Exception as e:
            self.logger.error(f"处理结果时出错: {e}")
            raise
        
    # 生命周期钩子
    async def on_init(self):
        """初始化钩子"""
        pass
        
    async def on_start(self):
        """启动钩子"""
        pass
        
    async def on_stop(self):
        """停止钩子"""
        pass
        
    async def handle_error(self, error: Exception):
        """错误处理钩子"""
        self.logger.error(f"服务错误: {error}")
        
    # 抽象方法
    async def get_methods(self) -> Dict[str, str]:
        """获取服务方法映射"""
        raise NotImplementedError("获取方法映射方法未实现")
        
    async def process_request(self, request: Dict) -> Any:
        """处理请求（用于 REQ/REP 和 ROUTER 模式）"""
        raise NotImplementedError("请求处理方法未实现")
        
    async def process_pipeline(self, data: Dict) -> Any:
        """处理管道数据（用于 PIPELINE 模式）"""
        raise NotImplementedError("管道处理方法未实现")
        
    async def generate_publication(self) -> AsyncGenerator[tuple, None]:
        """生成发布数据（用于 PUB/SUB 模式）"""
        raise NotImplementedError("发布生成方法未实现")
        
    async def process_message(
        self, 
        message: Optional[Dict] = None
    ) -> Union[AsyncGenerator, Any]:
        """统一的消息处理方法（可选实现）
        
        如果实现了这个方法，将优先使用；
        否则根据服务模式调用对应的专用方法。
        """
        if self.service_mode in (ServiceMode.REQUEST_REPLY, ServiceMode.ROUTER, ServiceMode.PUSH_PULL):
            return await self.process_request(message)
            
        elif self.service_mode == ServiceMode.PIPELINE:
            return await self.process_pipeline(message)
            
        elif self.service_mode == ServiceMode.PUB_SUB:
            return self.generate_publication()
            
