import asyncio
import logging
import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator, Optional

from illufly.mq.concurrency.base_runner import BaseRunner
from illufly.mq.models import ServiceConfig, StreamingBlock

logger = logging.getLogger(__name__)

class ThreadRunner(BaseRunner):
    """线程池执行器"""
    def __init__(self, config: ServiceConfig, max_workers: Optional[int] = None, **kwargs):
        super().__init__(config, **kwargs)
        self._max_workers = max_workers or (multiprocessing.cpu_count() * 5)
        self.executor = ThreadPoolExecutor(max_workers=self._max_workers)
        self._logger.debug(f"线程池初始化完成，最大工作线程数: {self._max_workers}")
        
    async def _handle_request(self, request: dict) -> dict:
        """在线程池中处理请求"""
        command = request.get("command", "process")
        session_id = request.get("session_id")
        prompt = request.get("prompt", "")
        kwargs = request.get("kwargs", {})
        
        if command == "process":
            if not self.service:
                return {"status": "success", "session_id": session_id}
                
            try:
                self._logger.info(f"提交任务到线程池，会话ID: {session_id}, 提示词: {prompt}")
                
                # 立即返回响应，不等待处理完成
                future = self.executor.submit(
                    self._thread_process_request,
                    prompt,
                    **kwargs
                )
                
                # 启动异步任务来处理结果
                asyncio.create_task(self._handle_thread_result(
                    future, session_id
                ))
                
                self._logger.info(f"任务已提交到线程池，会话ID: {session_id}")
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
                
    def _thread_process_request(self, prompt: str, **kwargs) -> list:
        """在线程中执行请求的独立函数"""
        thread_id = threading.current_thread().name
        self._logger.info(f"线程 {thread_id} 开始处理请求: {prompt}")
        
        try:
            blocks = []
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def process_generator():
                self._logger.info(f"线程 {thread_id} 开始生成响应")
                async for block in self.service._adapt_process_request(prompt, **kwargs):
                    block_dict = block.model_dump(exclude_none=True)
                    block_dict["thread_id"] = thread_id
                    blocks.append(block_dict)
                    self._logger.info(f"线程 {thread_id} 生成块: {block_dict}")
                    
            loop.run_until_complete(process_generator())
            self._logger.info(f"线程 {thread_id} 处理完成，生成了 {len(blocks)} 个块")
            return blocks
            
        except Exception as e:
            self._logger.error(f"线程处理出错: {e}")
            raise
        finally:
            loop.close()
            
    async def _handle_thread_result(self, future, session_id: str) -> None:
        """异步处理线程池的结果"""
        try:
            self._logger.info(f"开始处理线程结果，会话ID: {session_id}")
            blocks = await asyncio.get_event_loop().run_in_executor(
                None, future.result, 30.0
            )
            self._logger.info(f"收到线程结果，块数: {len(blocks)}")
            
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
            thread_id = blocks[-1]["thread_id"] if blocks else None
            await self.message_bus.publish(
                f"llm.{self.config.service_name}.{session_id}.complete",
                {
                    "status": "complete",
                    "session_id": session_id,
                    "service": self.config.service_name,
                    "thread_id": thread_id
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