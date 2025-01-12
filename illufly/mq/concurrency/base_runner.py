from abc import ABC, abstractmethod
from typing import AsyncIterator

import asyncio
import json
import logging
import uuid
import zmq.asyncio
import time

from ..models import ServiceConfig, StreamingBlock
from ..message_bus import MessageBusBase, MessageBusType, create_message_bus

class BaseRunner(ABC):
    """并发执行器基类 - 专注于服务端逻辑"""
    def __init__(self, config: ServiceConfig, service=None, message_bus=None, logger=None):
        self.config = config
        self.service = service  # service 可以为空
        self._logger = logger or logging.getLogger(__name__)
        self._running = False
        self.context = None
        self.mq_server = None
        self.message_bus = message_bus or create_message_bus(MessageBusType.INPROC)
        
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """确保有可用的事件循环，如果需要则创建新的"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
        
    def start(self) -> None:
        """同步启动服务端"""
        loop = self._ensure_loop()
        if loop.is_running():
            raise RuntimeError("Cannot call start() from an async context. Use start_async() instead.")
        loop.run_until_complete(self.start_async())
            
    async def start_async(self) -> None:
        """异步启动服务端"""
        if self._running:
            self._logger.debug("Runner already running")
            return
            
        self._logger.debug("Starting runner")
        try:
            # 初始化 ZMQ 资源
            self._logger.debug("Initializing ZMQ resources")
            self.context = zmq.asyncio.Context.instance()
            self.mq_server = self.context.socket(zmq.REP)
            self.mq_server.setsockopt(zmq.RCVHWM, self.config.max_requests)
            self.mq_server.setsockopt(zmq.SNDHWM, self.config.max_requests)
            self.mq_server.bind(self.config.mq_address)
            self._logger.debug(f"Server socket bound to {self.config.mq_address}")
                        
            self._running = True
            self._server_task = asyncio.create_task(self._run_server())
            self._logger.debug(f"Server task created: {self._server_task}")
            
            # 等待服务器真正启动
            await asyncio.sleep(0.1)
            
        except Exception as e:
            self._logger.error(f"Error starting runner: {e}")
            await self.stop_async()  # 确保清理资源
            raise
            
    def stop(self) -> None:
        """同步停止服务端"""
        loop = self._ensure_loop()
        if loop.is_running():
            raise RuntimeError("Cannot call stop() from an async context. Use stop_async() instead.")
        loop.run_until_complete(self.stop_async())
            
    async def stop_async(self) -> None:
        """异步停止服务端"""
        if not self._running:
            return
            
        self._logger.debug("Stopping server")
        self._running = False
        
        try:
            if self._server_task:
                self._logger.debug("Cancelling server task")
                self._server_task.cancel()
                try:
                    await self._server_task
                except asyncio.CancelledError:
                    self._logger.debug("Server task cancelled as expected")
                    
            if self.mq_server:
                self._logger.debug("Closing server socket")
                self.mq_server.close(linger=0)
                self.mq_server = None
                
            self._logger.debug("Server stopped")
            
        except Exception as e:
            self._logger.error(f"Error stopping server: {e}")
            raise
        
    async def _run_server(self):
        """运行服务器循环"""
        self._logger.info(f"Server loop starting on {self.config.mq_address}")
        try:
            while self._running:
                try:
                    # 添加超时控制
                    request = await asyncio.wait_for(
                        self.mq_server.recv_json(),
                        timeout=1.0
                    )
                    self._logger.debug(f"Received request: {request}")
                    
                    # 处理请求
                    response = await self._handle_request(request)
                    
                    # 发送响应
                    await self.mq_server.send_json(response)
                    
                except asyncio.TimeoutError:
                    continue
                
        except asyncio.CancelledError:
            self._logger.info("Server loop cancelled")
            raise
        except Exception as e:
            self._logger.error(f"Server loop error: {e}")
            raise
        finally:
            self._logger.info("Server loop ended")

    async def _handle_request(self, request: dict) -> dict:
        """处理单个请求并返回响应"""
        try:
            command = request.get("command", "process")
            self._logger.info(f"Handling {command} request")
            
            if command == "init":
                session_id = str(uuid.uuid4())
                topic = f"llm.{self.config.service_name}.{session_id}"
                self._logger.info(f"Initialized new session: {session_id} with topic: {topic}")
                return {
                    "status": "success",
                    "session_id": session_id,
                    "topic": topic
                }
                
            elif command == "process":
                session_id = request["session_id"]
                prompt = request["prompt"]
                kwargs = request.get("kwargs", {})
                self._logger.info(f"Processing request for session {session_id}")
                
                if prompt is None:
                    raise ValueError("Prompt cannot be None")
                    
                if not isinstance(prompt, str):
                    raise TypeError(f"Prompt must be string, got {type(prompt)}")
                    
                if not prompt.strip():
                    raise ValueError("Prompt cannot be empty")
                
                # 发布处理结果
                if self.service:
                    self._logger.info("Processing with service instance")
                    async for block in self.service._adapt_process_request(prompt, **kwargs):
                        event_dict = block.model_dump(exclude_none=True)
                        event_dict["session_id"] = session_id
                        event_dict["service"] = self.config.service_name
                        await self.message_bus.publish(
                            f"llm.{self.config.service_name}.{session_id}",
                            event_dict
                        )
                else:
                    self._logger.info("Using test service response")
                    await self.message_bus.publish(
                        f"llm.{self.config.service_name}.{session_id}",
                        {
                            "session_id": session_id,
                            "service": self.config.service_name,
                            "content": f"Test response for: {prompt}",
                            "block_type": "text"
                        }
                    )
                
                # 发送完成通知
                self._logger.info("Publishing completion notice")
                await self.message_bus.publish(
                    f"llm.{self.config.service_name}.{session_id}.complete",
                    {
                        "status": "complete",
                        "session_id": session_id,
                        "service": self.config.service_name
                    }
                )
                
                self._logger.info("Sending success response")
                return {
                    "status": "success",
                    "session_id": session_id
                }
                
        except Exception as e:
            self._logger.error(f"Error handling request: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
