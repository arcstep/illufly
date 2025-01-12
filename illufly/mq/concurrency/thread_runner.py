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
        logger.info(f"创建线程池执行器：{config.service_name}, 最大工作线程数: {self._max_workers}, 其他参数：{kwargs}")
        
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
                
                # 提交任务到线程池，传入 session_id
                self.executor.submit(
                    self._thread_process_request,
                    prompt,
                    session_id,
                    **kwargs
                )
                
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
                
    def _thread_process_request(self, prompt: str, session_id: str, **kwargs) -> None:
        """在线程中执行请求并直接发布结果"""
        thread_id = threading.current_thread().name
        self._logger.info(
            f"[ThreadRunner] 线程 {thread_id} 开始处理请求 - "
            f"会话ID: {session_id}, "
            f"提示词: {prompt}"
        )
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def process_generator():
                try:
                    self._logger.info(f"[ThreadRunner] 线程 {thread_id} 开始生成响应")
                    async for block in self.service._adapt_process_request(prompt, **kwargs):
                        block_dict = block.model_dump(exclude_none=True)
                        block_dict["thread_id"] = thread_id
                        
                        topic = f"llm.{self.config.service_name}.{session_id}"
                        message = {
                            **block_dict,
                            "session_id": session_id,
                            "service": self.config.service_name
                        }
                        
                        self._logger.debug(
                            f"[ThreadRunner] 线程 {thread_id} 准备发布消息 - "
                            f"主题: {topic}, "
                            f"消息: {message}"
                        )
                        
                        await self.message_bus.publish(topic, message)
                        self._logger.debug(f"[ThreadRunner] 线程 {thread_id} 发布成功")
                        
                    # 发送完成消息
                    complete_topic = f"llm.{self.config.service_name}.{session_id}.complete"
                    self._logger.debug(f"[ThreadRunner] 线程 {thread_id} 准备发送完成消息")
                    await self.message_bus.publish(
                        complete_topic,
                        {
                            "status": "complete",
                            "session_id": session_id,
                            "service": self.config.service_name,
                            "thread_id": thread_id
                        }
                    )
                except Exception as e:
                    self._logger.error(f"[ThreadRunner] 线程 {thread_id} 生成响应时出错: {e}")
                    error_topic = f"llm.{self.config.service_name}.{session_id}.error"
                    await self.message_bus.publish(
                        error_topic,
                        {
                            "status": "error",
                            "error": str(e),
                            "session_id": session_id,
                            "service": self.config.service_name,
                            "thread_id": thread_id
                        }
                    )
                    
            loop.run_until_complete(process_generator())
            
        except Exception as e:
            self._logger.error(f"线程处理出错: {e}")
            raise
        finally:
            loop.close()