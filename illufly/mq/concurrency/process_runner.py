import asyncio
import json
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import AsyncIterator
import zmq.asyncio
from pydantic import BaseModel

from .base_runner import BaseRunner
from ..models import ServiceConfig, StreamingBlock
from ..message_bus import MessageBus

class ProcessContext(BaseModel):
    """进程上下文"""
    config: ServiceConfig
    running: bool = True
    
    def setup_logging(self) -> logging.Logger:
        return logging.getLogger(self.config.service_name)

class ProcessRunner(BaseRunner):
    """进程池执行器"""
    def __init__(self, config: ServiceConfig, max_workers: int = None):
        super().__init__(config)
        self._max_workers = max_workers or (multiprocessing.cpu_count())
        self.executor = ProcessPoolExecutor(max_workers=self._max_workers)
        self._server_process = None
        self._process_context = None
        self.message_bus = None
        self.context = None
        self.mq_server = None
        
    async def start(self):
        """启动进程池执行器"""
        if self._running:
            return
            
        # 初始化主进程资源
        self.context = zmq.asyncio.Context.instance()
        self.message_bus = MessageBus.instance()
        self.message_bus.start()
        
        # 创建进程上下文
        self._process_context = ProcessContext(
            config=self.config,
            running=True
        )
        
        # 启动工作进程
        self._server_process = multiprocessing.Process(
            target=self._process_worker,
            args=(self._process_context.model_dump(),),
            daemon=True
        )
        self._server_process.start()
        self._running = True
        
    async def stop(self):
        """停止进程池执行器"""
        if not self._running:
            return
            
        self._running = False
        
        # 停止工作进程
        if self._server_process:
            self._server_process.terminate()
            self._server_process.join(timeout=5.0)
            
        # 清理资源
        self.executor.shutdown(wait=True)
        if self.message_bus:
            self.message_bus.release()
        if self.context:
            self.context.term()
            
    async def process(self, prompt: str, session_id: str) -> AsyncIterator[StreamingBlock]:
        """在进程池中处理请求"""
        if not self._running:
            raise RuntimeError("ProcessRunner not running")
            
        # 在进程池中执行请求
        future = self.executor.submit(
            self._process_request,
            prompt,
            session_id
        )
        
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                future.result
            )
            async for event in result:
                yield event
        except Exception as e:
            self.logger.error(f"Process request error: {e}")
            yield StreamingBlock(
                block_type="error",
                error=str(e)
            ) 