import asyncio
import json
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import AsyncIterator
import zmq.asyncio
from pydantic import BaseModel
import importlib
from typing import Type
import resource
import os
import psutil

from .base_runner import BaseRunner
from ..models import ServiceConfig, StreamingBlock
from ..message_bus import MessageBus

class ProcessContext(BaseModel):
    """进程上下文"""
    config: ServiceConfig
    running: bool = True
    
    def setup_logging(self) -> logging.Logger:
        return logging.getLogger(self.config.service_name)

def _process_in_subprocess(config_dict: dict, prompt: str, **kwargs):
    """在子进程中执行请求的独立函数"""
    process_id = multiprocessing.current_process().name
    logger = logging.getLogger(__name__)
    logger.debug(f"子进程 {process_id} 开始处理请求")
    
    try:
        # 从配置字典重建配置
        config = ServiceConfig(**config_dict)
        
        # 动态导入服务类
        module_path = config_dict.get("service_module")
        class_name = config_dict.get("class_name")
        if not module_path or not class_name:
            raise ValueError("Missing service_module or class_name in config")
            
        module = importlib.import_module(module_path)
        ServiceClass = getattr(module, class_name)
        
        # 创建服务实例
        service = ServiceClass(config)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            blocks = []
            async def process_generator():
                async for block in service._adapt_process_request(prompt, **kwargs):
                    block_dict = block.model_dump(exclude_none=True)
                    block_dict["process_id"] = process_id
                    blocks.append(block_dict)
                    
            loop.run_until_complete(process_generator())
            logger.debug(f"子进程 {process_id} 处理完成")
            return blocks
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"子进程处理出错: {e}")
        raise

class ProcessRunner(BaseRunner):
    """进程池执行器"""
    def __init__(self, config, max_workers: int = None, **kwargs):
        super().__init__(config, **kwargs)
        
        # 获取系统限制
        soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NPROC)
        self._logger.info(f"系统进程数限制 - 软限制: {soft_limit}, 硬限制: {hard_limit}")
        
        # CPU信息
        cpu_count = multiprocessing.cpu_count()
        self._logger.info(f"CPU核心数: {cpu_count}")
        
        # 当前进程信息
        self._logger.info(f"当前进程ID: {os.getpid()}, 父进程ID: {os.getppid()}")
        
        # 进程池配置
        self._max_workers = max(2, max_workers or cpu_count)
        self._logger.info(f"进程池配置 - 最大工作进程数: {self._max_workers}")
        
        # 使用 'spawn' 上下文创建进程池
        ctx = multiprocessing.get_context('spawn')
        self.executor = ProcessPoolExecutor(
            max_workers=self._max_workers,
            mp_context=ctx,
            initializer=self._process_initializer,
            initargs=(self._logger.level,)
        )
        
        # 进程池状态
        self._logger.info(f"进程池初始化完成 - 上下文类型: {ctx.get_start_method()}")
        
    @staticmethod
    def _process_initializer(log_level):
        """进程初始化函数"""
        logging.basicConfig(level=log_level)
        logger = logging.getLogger(__name__)
        process = psutil.Process() if psutil else None
        
        logger.info(
            f"初始化子进程 - "
            f"进程ID: {os.getpid()}, "
            f"父进程ID: {os.getppid()}, "
            f"内存使用: {process.memory_info().rss / 1024 / 1024:.1f}MB" if process else "内存信息不可用"
        )
        
    async def _handle_request(self, request: dict) -> dict:
        """在进程池中处理请求"""
        try:
            command = request.get("command", "process")
            session_id = request.get("session_id")
            prompt = request.get("prompt", "")
            kwargs = request.get("kwargs", {})
            
            if command == "process":
                if not self.service:
                    return {"status": "success", "session_id": session_id}
                    
                try:
                    self._logger.debug(f"提交任务到进程池，会话ID: {session_id}")
                    config_dict = self.config.model_dump()
                    config_dict["class_name"] = self.service.__class__.__name__
                    config_dict["service_module"] = self.service.__class__.__module__
                    
                    # 立即返回响应，不等待处理完成
                    future = self.executor.submit(
                        _process_in_subprocess,
                        config_dict,
                        prompt,
                        **kwargs
                    )
                    
                    # 启动异步任务来处理结果
                    asyncio.create_task(self._handle_process_result(
                        future, session_id
                    ))
                    
                    return {
                        "status": "success", 
                        "session_id": session_id
                    }
                    
                except Exception as e:
                    error_msg = str(e)
                    self._logger.error(f"处理请求时出错: {error_msg}")
                    return {
                        "status": "error",
                        "error": error_msg,
                        "session_id": session_id
                    }
            else:
                return await super()._handle_request(request)
                
        except Exception as e:
            self._logger.error(f"处理请求时出错: {e}")
            return {
                "status": "error",
                "error": str(e),
                "session_id": session_id if session_id else None
            }
            
    async def _handle_process_result(self, future, session_id):
        """异步处理进程池的结果"""
        try:
            blocks = await asyncio.get_event_loop().run_in_executor(
                None, future.result, 30.0
            )
            
            # 发布结果
            for block in blocks:
                await self.message_bus.publish(
                    f"llm.{self.config.service_name}.{session_id}",
                    {
                        **block,
                        "session_id": session_id,
                        "service": self.config.service_name
                    }
                )
            
            # 发送完成消息
            process_id = blocks[-1]["process_id"] if blocks else None
            await self.message_bus.publish(
                f"llm.{self.config.service_name}.{session_id}.complete",
                {
                    "status": "complete",
                    "session_id": session_id,
                    "service": self.config.service_name,
                    "process_id": process_id
                }
            )
        except Exception as e:
            self._logger.error(f"处理结果时出错: {e}")
            await self.message_bus.publish(
                f"llm.{self.config.service_name}.{session_id}.error",
                {
                    "status": "error",
                    "error": str(e),
                    "session_id": session_id,
                    "service": self.config.service_name
                }
            )
            
    async def stop_async(self) -> None:
        """停止进程池执行器"""
        if not self._running:
            return
            
        await super().stop_async()
        self.executor.shutdown(wait=True) 