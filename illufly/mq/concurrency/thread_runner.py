import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator
import zmq.asyncio

from .base_runner import BaseRunner
from ..models import StreamingBlock
from ..message_bus import MessageBus

class ThreadRunner(BaseRunner):
    """线程池执行器"""
    def __init__(self, config, max_workers: int = None, **kwargs):
        super().__init__(config, **kwargs)
        self._max_workers = max_workers or (threading.active_count() + 4)
        self.executor = ThreadPoolExecutor(max_workers=self._max_workers)
        
    async def _handle_request(self, request: dict) -> dict:
        """在线程池中处理请求"""
        try:
            command = request.get("command", "process")
            session_id = request.get("session_id")
            prompt = request.get("prompt", "")
            kwargs = request.get("kwargs", {})
            
            if command == "process":
                if not self.service:
                    return {"status": "success", "session_id": session_id}
                    
                # 在线程池中执行请求
                def run_in_thread():
                    async def process_generator():
                        async for block in self.service._adapt_process_request(prompt, **kwargs):
                            yield block
                            
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        blocks = []
                        async_gen = process_generator()
                        while True:
                            try:
                                block = loop.run_until_complete(async_gen.__anext__())
                                blocks.append(block)
                            except StopAsyncIteration:
                                break
                        return blocks
                    finally:
                        loop.close()
                
                try:
                    future = self.executor.submit(run_in_thread)
                    blocks = future.result(timeout=30.0)
                    
                    # 发布结果
                    for block in blocks:
                        event_dict = block.model_dump(exclude_none=True)
                        event_dict["session_id"] = session_id
                        event_dict["service"] = self.config.service_name
                        await self.message_bus.publish(
                            f"llm.{self.config.service_name}.{session_id}",
                            event_dict
                        )
                    
                    # 发送完成消息
                    await self.message_bus.publish(
                        f"llm.{self.config.service_name}.{session_id}.complete",
                        {
                            "status": "complete",
                            "session_id": session_id,
                            "service": self.config.service_name
                        }
                    )
                        
                    return {"status": "success", "session_id": session_id}
                    
                except TimeoutError:
                    # 发送错误消息
                    await self.message_bus.publish(
                        f"llm.{self.config.service_name}.{session_id}.error",
                        {
                            "status": "error",
                            "error": "Request timeout",
                            "session_id": session_id,
                            "service": self.config.service_name
                        }
                    )
                    return {
                        "status": "error",
                        "error": "Request timeout",
                        "session_id": session_id
                    }
                    
            else:
                return await super()._handle_request(request)
                
        except Exception as e:
            self._logger.error(f"Error handling request: {e}")
            if session_id:
                # 发送错误消息
                await self.message_bus.publish(
                    f"llm.{self.config.service_name}.{session_id}.error",
                    {
                        "status": "error",
                        "error": str(e),
                        "session_id": session_id,
                        "service": self.config.service_name
                    }
                )
            return {
                "status": "error",
                "error": str(e),
                "session_id": session_id if session_id else None
            }
            
    async def stop_async(self) -> None:
        """停止线程池执行器"""
        if not self._running:
            return
            
        await super().stop_async()
        self.executor.shutdown(wait=True) 