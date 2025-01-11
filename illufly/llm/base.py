import asyncio
import threading
import zmq.asyncio
import uuid
import logging
import time

from typing import Union, List, AsyncGenerator, Optional
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from enum import Enum
from abc import ABC, abstractmethod

from ..types import EventBlock

class ConcurrencyStrategy(Enum):
    ASYNC = "async"
    THREAD_POOL = "thread_pool"
    PROCESS_POOL = "process_pool"

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
        self.logger = logger or logging.getLogger(__name__)

        self.service_name = service_name or self.__class__.__name__
        self.concurrency = concurrency or ConcurrencyStrategy.ASYNC
        self._init_zmq(self.service_name)
        self._setup_concurrency(max_workers)
        self.logger.info(f"Initializing {self.__class__.__name__} with strategy: {self.concurrency}")
        self._running = True
        self._server_task = None

    def _init_zmq(self, service_name: str):
        """初始化ZMQ连接"""
        self.context = (
            zmq.asyncio.Context.instance() 
            if self.concurrency == ConcurrencyStrategy.PROCESS_POOL 
            else zmq.asyncio.Context()
        )
        
        self.mq_server = self.context.socket(zmq.REP)
        self.pub_socket = self.context.socket(zmq.PUB)
        
        service_id = service_name or self.__class__.__name__
        self.mq_address = f"inproc://{service_id}"
        self.pub_address = f"inproc://{service_id}_PUB"
        self.logger.info(f"Setting up ZMQ sockets for service: {service_name}")
        self.logger.debug(f"ZMQ addresses - REP: {self.mq_address}, PUB: {self.pub_address}")

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
        """启动服务"""
        self.logger.info(f"Starting service with {self.concurrency.value} strategy")
        self.mq_server.bind(self.mq_address)
        self.pub_socket.bind(self.pub_address)
        
        if self.concurrency == ConcurrencyStrategy.ASYNC:
            self._server_task = asyncio.create_task(self.run_server())
        else:
            self._server_thread = threading.Thread(target=self._thread_run_server, daemon=True)
            self._server_thread.start()

    def _thread_run_server(self):
        """线程服务运行器"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.run_server())

    async def run_server(self):
        """服务主循环"""
        self.logger.info("Server loop started")
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self.mq_server.recv_json(),
                    timeout=0.1  # 添加超时以便检查停止标志
                )
                prompt = message.get("prompt", "")
                
                session_id = str(uuid.uuid4())
                await self.mq_server.send_json({"session_id": session_id})
                
                if self.concurrency == ConcurrencyStrategy.ASYNC:
                    asyncio.create_task(self.handle_stream(prompt, session_id))
                else:
                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(self.executor, 
                        lambda: asyncio.run(self.handle_stream(prompt, session_id)))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Error in server loop: {str(e)}")
                if not self._running:
                    break

    async def handle_stream(self, prompt: str, session_id: str):
        """处理流式响应"""
        self.logger.debug(f"Processing stream for session: {session_id[:8]}...")
        try:
            async for event in self.process_request(prompt):
                event_dict = event.__dict__
                event_dict["session_id"] = session_id
                await self.pub_socket.send_json(event_dict)
            self.logger.debug(f"Stream completed for session: {session_id[:8]}")
        except Exception as e:
            self.logger.error(f"Error in stream processing for session {session_id[:8]}: {str(e)}")
            raise

    @abstractmethod
    async def process_request(self, prompt: str, **kwargs):
        """处理请求的抽象方法，子类必须实现"""
        pass

    def __call__(self, prompt: str) -> AsyncGenerator[EventBlock, None]:
        """客户端调用接口"""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(self.executor, self.sync_call, prompt)

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
        self.logger.info("Stopping service...")
        self._running = False
        
        # 等待服务器任务完成
        if self._server_task:
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
        
        # 关闭sockets
        self.mq_server.close()
        self.pub_socket.close()
        
        # 关闭执行器
        if self.executor:
            self.executor.shutdown(wait=False)
        
        # 关闭context
        self.context.term()
        
        self.logger.info("Service stopped") 