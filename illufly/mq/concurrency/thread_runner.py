import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator
import zmq.asyncio

from .base import BaseRunner
from ..models import StreamingBlock
from ..message_bus import MessageBus

class ThreadRunner(BaseRunner):
    """线程池执行器"""
    def __init__(self, config, max_workers: int = None):
        super().__init__(config)
        self._server_thread = None
        self._max_workers = max_workers or (threading.active_count() + 4)
        self.executor = ThreadPoolExecutor(max_workers=self._max_workers)
        self._thread_loop = None
        
    async def start(self):
        """启动线程池执行器"""
        if self._running:
            self.logger.warning("ThreadRunner already running")
            return
            
        self.logger.info(f"Starting ThreadRunner with {self._max_workers} workers")
        try:
            self._initialize_zmq()
            self.mq_server.bind(self.config.mq_address)
            self._running = True
            
            # 在新线程中运行事件循环
            self._server_thread = threading.Thread(
                target=self._thread_run_server,
                daemon=True
            )
            self._server_thread.start()
            self.logger.info("ThreadRunner started")
        except Exception as e:
            self.logger.error(f"Failed to start ThreadRunner: {e}")
            self._cleanup_zmq()
            raise
            
    async def stop(self):
        """停止线程池执行器"""
        if not self._running:
            return
            
        self.logger.info("Stopping ThreadRunner")
        self._running = False
        
        # 等待线程结束
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=5.0)
            if self._server_thread.is_alive():
                self.logger.warning("Server thread did not stop gracefully")
                
        # 关闭线程池
        self.executor.shutdown(wait=True)
        self._cleanup_zmq()
        self.logger.info("ThreadRunner stopped")
        
    def _thread_run_server(self):
        """在新线程中运行事件循环"""
        try:
            self._thread_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._thread_loop)
            self._thread_loop.run_until_complete(self._run_server())
        except Exception as e:
            self.logger.error(f"Thread server error: {e}")
        finally:
            self._thread_loop.close()
            
    async def _run_server(self):
        """服务器主循环"""
        self.logger.info("Server loop started")
        
        while self._running:
            try:
                message = await self.mq_server.recv_json()
                session_id = message.get("session_id")
                prompt = message.get("prompt", "")
                
                if not session_id:
                    await self.mq_server.send_json({
                        "status": "error",
                        "error": "Missing session_id"
                    })
                    continue
                
                self.logger.info(f"Processing request {session_id[:8]}...")
                
                try:
                    # 在线程池中处理请求
                    future = self.executor.submit(
                        asyncio.run,
                        self._process_and_publish(prompt, session_id)
                    )
                    
                    # 等待处理完成
                    try:
                        future.result(timeout=30.0)
                        await self.mq_server.send_json({
                            "status": "completed",
                            "session_id": session_id
                        })
                    except TimeoutError:
                        await self.mq_server.send_json({
                            "status": "timeout",
                            "session_id": session_id
                        })
                except Exception as e:
                    self.logger.error(f"Error processing {session_id[:8]}: {str(e)}")
                    await self.mq_server.send_json({
                        "status": "error",
                        "session_id": session_id,
                        "error": str(e)
                    })
                    
            except Exception as e:
                self.logger.error(f"Server loop error: {str(e)}")
                if not self._running:
                    break
                    
    async def _process_and_publish(self, prompt: str, session_id: str):
        """处理请求并发布结果"""
        try:
            async for event in self.process_request(prompt, session_id):
                event_dict = event.model_dump()
                event_dict["session_id"] = session_id
                event_dict["service"] = self.config.service_name
                
                await self.message_bus.socket.send_multipart([
                    f"llm.{self.config.service_name}.{session_id}".encode(),
                    json.dumps(event_dict).encode()
                ])
                
        except Exception as e:
            self.logger.error(f"Error in {session_id[:8]}: {str(e)}")
            await self.message_bus.socket.send_multipart([
                f"llm.{self.config.service_name}.{session_id}.error".encode(),
                json.dumps({"error": str(e)}).encode()
            ])
            raise 