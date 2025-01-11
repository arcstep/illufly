import asyncio
import threading
import zmq.asyncio
import uuid
import logging
import time
import multiprocessing
import json

from typing import Union, List, AsyncGenerator, Optional
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from enum import Enum
from abc import ABC, abstractmethod

from ..types import EventBlock

class ConcurrencyStrategy(Enum):
    ASYNC = "async"
    THREAD_POOL = "thread_pool"
    PROCESS_POOL = "process_pool"

class MessageBus:
    """全局消息总线"""
    _instance = None
    _context = None
    _pub_socket = None
    _lock = threading.Lock()
    _ref_count = 0
    _started = False  # 添加启动状态标志
    
    @classmethod
    def instance(cls):
        """获取消息总线实例（但不启动）"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        cls._ref_count += 1
        return cls._instance
    
    def start(self):
        """显式启动消息总线"""
        with self._lock:
            if not self._started:
                self._context = zmq.asyncio.Context.instance()
                self._pub_socket = self._context.socket(zmq.PUB)
                self._pub_socket.bind("inproc://message_bus")
                self._started = True
                logging.getLogger(__name__).info(
                    "Global message bus started at inproc://message_bus"
                )
    
    @property
    def is_started(self):
        """检查消息总线是否已启动"""
        return self._started
    
    @property
    def socket(self):
        """获取发布socket（如果未启动则抛出异常）"""
        if not self._started:
            raise RuntimeError("Message bus not started. Call start() first.")
        return self._pub_socket
    
    @property
    def address(self):
        """获取消息总线地址"""
        return "inproc://message_bus"
    
    @classmethod
    def release(cls):
        """释放消息总线实例"""
        with cls._lock:
            if cls._ref_count > 0:
                cls._ref_count -= 1
                if cls._ref_count == 0 and cls._instance:
                    if cls._pub_socket:
                        cls._pub_socket.close(linger=0)
                    if cls._context:
                        cls._context.term()
                    cls._instance = None
                    cls._context = None
                    cls._pub_socket = None
                    cls._started = False
                    logging.getLogger(__name__).info(
                        "Message bus cleaned up"
                    )

class BaseStreamingService(ABC):
    """基础流式服务类"""

    def __init__(
        self, 
        service_name: str = None,
        concurrency: ConcurrencyStrategy = None,
        max_workers: int = None,
        logger: logging.Logger = None
    ):
        """初始化服务"""
        # 先设置基本属性
        self.service_name = service_name or self.__class__.__name__
        self.concurrency = concurrency or ConcurrencyStrategy.ASYNC
        self.logger = logger or logging.getLogger(__name__)
        
        # 然后再使用这些属性进行日志记录
        self.logger.info(f"Initializing {self.__class__.__name__} with strategy: {self.concurrency}")
        
        # 初始化地址，但不创建 socket
        self.mq_address = f"inproc://{self.service_name}"
        self.logger.info(f"Service address will be: {self.mq_address}")
        
        # 获取并启动消息总线
        self.message_bus = MessageBus.instance()
        self.message_bus.start()  # 显式启动
        self.logger.info("Message bus started")
        
        self._setup_concurrency(max_workers)
        self._running = False
        self._server_task = None
        self._last_log_time = 0
        
        # 延迟创建 socket 到 start 方法
        self.context = None
        self.mq_server = None

    def _setup_concurrency(self, max_workers: Optional[int]):
        """设置并发策略"""
        if self.concurrency == ConcurrencyStrategy.ASYNC:
            self.executor = None
        elif self.concurrency == ConcurrencyStrategy.THREAD_POOL:
            self.executor = ThreadPoolExecutor(max_workers=max_workers)
        elif self.concurrency == ConcurrencyStrategy.PROCESS_POOL:
            self.executor = ProcessPoolExecutor(max_workers=max_workers)
        if self.concurrency != ConcurrencyStrategy.ASYNC:
            self.logger.info(f"Setting up {self.concurrency.value} with {max_workers} workers")

    def start(self):
        """根据不同的并发策略启动服务"""
        if self._running:
            self.logger.warning("Service already running")
            return
            
        self.logger.info(f"Starting service with {self.concurrency.value} strategy")
        
        # 创建 socket
        self.context = zmq.asyncio.Context.instance()
        self.mq_server = self.context.socket(zmq.REP)
        
        try:
            self.logger.info(f"Binding to {self.mq_address}")
            self.mq_server.bind(self.mq_address)
            self._running = True
            
            if self.concurrency == ConcurrencyStrategy.ASYNC:
                self._server_task = asyncio.create_task(self.run_server())
                self.logger.info("Async server task created")
            elif self.concurrency == ConcurrencyStrategy.THREAD_POOL:
                self._server_thread = threading.Thread(target=self._thread_run_server)
                self._server_thread.daemon = True
                self._server_thread.start()
                self.logger.info("Thread server started")
            else:  # PROCESS_POOL
                self._server_process = multiprocessing.Process(target=self._process_run_server)
                self._server_process.daemon = True
                self._server_process.start()
                self.logger.info("Process server started")
        except zmq.error.ZMQError as e:
            self.logger.error(f"Failed to bind socket: {e}")
            if self.mq_server:
                self.mq_server.close(linger=0)
            self.mq_server = None
            self.context = None
            raise

    def _thread_run_server(self):
        """线程模式的服务器循环"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run_server())
        finally:
            loop.close()

    def _process_run_server(self):
        """进程模式的服务器循环"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.run_server())
        finally:
            loop.close()

    async def run_server(self):
        """服务器主循环"""
        self.logger.info("Server loop started")
        loop_count = 0
        
        while self._running:
            try:
                current_time = time.time()
                # 每30秒输出一次心跳日志
                if current_time - self._last_log_time >= 30:
                    self.logger.info(f"Server heartbeat - Processed {loop_count} requests")
                    self._last_log_time = current_time
                    loop_count = 0
                
                message = await asyncio.wait_for(
                    self.mq_server.recv_json(),
                    timeout=0.1
                )
                prompt = message.get("prompt", "")
                session_id = message.get("session_id", str(uuid.uuid4()))  # 使用客户端提供的session_id
                
                self.logger.info(f"Received request - Session ID: {session_id[:8]}...")
                await self.mq_server.send_json({"session_id": session_id})  # 返回相同的session_id
                
                asyncio.create_task(self.handle_request(prompt, session_id))
                loop_count += 1
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Error in server loop: {str(e)}")
                if not self._running:
                    break

    async def handle_request(self, prompt: str, session_id: str):
        """处理单个请求"""
        try:
            self.logger.info(f"Processing request - Session ID: {session_id[:8]}...")
            async for event in self.process_request(prompt):
                event_dict = event.model_dump()
                event_dict["session_id"] = session_id
                event_dict["service"] = self.service_name
                
                # 通过消息总线发布
                self.logger.info(f"Publishing {event.block_type} for {session_id[:8]}...")
                await self.message_bus.socket.send_multipart([
                    f"llm.{self.service_name}.{session_id}".encode(),
                    json.dumps(event_dict).encode()
                ])
        except Exception as e:
            self.logger.error(f"Error in {session_id[:8]}: {str(e)}")
            await self.message_bus.socket.send_multipart([
                f"llm.{self.service_name}.{session_id}.error".encode(),
                json.dumps({"error": str(e)}).encode()
            ])

    @abstractmethod
    async def process_request(self, prompt: str, **kwargs):
        """处理请求的抽象方法，子类必须实现"""
        pass

    async def __call__(self, prompt: str, **kwargs) -> AsyncGenerator[EventBlock, None]:
        """客户端调用"""
        self.logger.info("Client: Starting request...")
        req_socket = self.context.socket(zmq.REQ)
        sub_socket = self.context.socket(zmq.SUB)
        
        try:
            # 连接到服务的 REQ socket 和全局消息总线
            req_socket.connect(self.mq_address)
            sub_socket.connect(self.message_bus.address)
            
            # 先订阅，再发送请求
            session_id = str(uuid.uuid4())
            topic = f"llm.{self.service_name}.{session_id}"
            self.logger.info(f"Client: Pre-subscribing to {topic}")
            sub_socket.subscribe(topic.encode())
            
            # 给订阅一点时间建立
            await asyncio.sleep(0.1)
            
            # 发送请求，包含session_id
            self.logger.info(f"Client: Sending request with session {session_id[:8]}")
            await req_socket.send_json({
                "prompt": prompt,
                "session_id": session_id  # 发送session_id给服务端
            })
            response = await req_socket.recv_json()
            
            # 验证返回的session_id
            if response["session_id"] != session_id:
                raise RuntimeError("Session ID mismatch")
            
            self.logger.info(f"Client: Starting to receive messages for {session_id[:8]}")
            while True:
                try:
                    self.logger.info("Client: Waiting for next message...")
                    topic, data = await asyncio.wait_for(
                        sub_socket.recv_multipart(),
                        timeout=5.0
                    )
                    topic = topic.decode()
                    event_dict = json.loads(data.decode())
                    self.logger.info(f"Client: Received message on {topic}")
                    
                    if ".error" in topic:
                        raise Exception(event_dict.get("error"))
                        
                    event = EventBlock.model_validate(event_dict)
                    self.logger.info(f"Client: Processing {event.block_type} event")
                    yield event
                    if event.block_type == "end":
                        break
                except asyncio.TimeoutError:
                    self.logger.error("Client: Timeout waiting for messages")
                    break
        finally:
            self.logger.info("Client: Cleaning up sockets")
            req_socket.close(linger=0)
            sub_socket.close(linger=0)

    def sync_call(self, prompt: str) -> AsyncGenerator[EventBlock, None]:
        """同步客户端调用实现"""
        req_socket = self.context.socket(zmq.REQ)
        req_socket.connect(self.mq_address)
        
        sub_socket = self.context.socket(zmq.SUB)
        sub_socket.connect(self.pub_address)
        
        session_start_time = time.time()
        try:
            req_socket.send_json({"prompt": prompt})
            response = req_socket.recv_json()
            session_id = response["session_id"]
            self.logger.info(f"Client connected with session: {session_id[:8]}...")
            
            sub_socket.subscribe(session_id.encode())
            
            event_count = 0
            while True:
                event_dict = sub_socket.recv_json()
                if event_dict["session_id"] == session_id:
                    event_count += 1
                    if event_dict.get("block_type") == "end":
                        duration = time.time() - session_start_time
                        self.logger.info(
                            f"Session {session_id[:8]} completed: "
                            f"{event_count} events in {duration:.2f}s"
                        )
                        break
                    yield EventBlock(**event_dict)
        except Exception as e:
            self.logger.error(f"Error in client call: {str(e)}")
            raise
        finally:
            req_socket.close()
            sub_socket.close() 

    async def cleanup(self):
        """清理服务资源"""
        self.logger.info("Cleaning up service resources")
        if hasattr(self, 'mq_server'):
            self.mq_server.close()
        if hasattr(self, 'pub_socket'):
            self.pub_socket.close()
        if hasattr(self, 'context'):
            self.context.term()
        if hasattr(self, 'executor') and self.executor:
            self.executor.shutdown(wait=True) 

    async def stop(self):
        """停止服务"""
        if not self._running:
            self.logger.warning("Service not running")
            return
            
        self.logger.info("Stopping service...")
        self._running = False
        
        if self.concurrency == ConcurrencyStrategy.ASYNC:
            if self._server_task:
                await self._server_task
                self.logger.info("Async server task stopped")
        elif self.concurrency == ConcurrencyStrategy.THREAD_POOL:
            if hasattr(self, '_server_thread'):
                self._server_thread.join()
                self.logger.info("Thread server stopped")
        else:  # PROCESS_POOL
            if hasattr(self, '_server_process'):
                self._server_process.join()
                self.logger.info("Process server stopped")
        
        # 清理资源
        if self.mq_server:
            self.logger.info("Closing server socket")
            self.mq_server.close(linger=0)
            self.mq_server = None
        
        self.context = None
        # 释放消息总线
        MessageBus.release()
        self.logger.info("Service cleanup completed") 