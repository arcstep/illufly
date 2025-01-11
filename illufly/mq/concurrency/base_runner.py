from abc import ABC, abstractmethod
import asyncio
import json
import logging
import uuid
from typing import AsyncIterator
import zmq.asyncio

from ..models import ServiceConfig, StreamingBlock
from ..message_bus import MessageBus

class BaseRunner(ABC):
    """并发执行器基类 - 专注于服务端逻辑"""
    def __init__(self, config: ServiceConfig, service=None, logger=None):
        self.config = config
        self.service = service  # service 可以为空
        self._logger = logger or logging.getLogger(__name__)
        self._running = False
        self.context = None
        self.mq_server = None
        self.message_bus = None
        
    async def start(self):
        """启动服务端"""
        if self._running:
            self._logger.debug("Runner already running")
            return
            
        self._logger.debug("Initializing ZMQ resources")
        self.context = zmq.asyncio.Context.instance()
        self.mq_server = self.context.socket(zmq.REP)
        self.mq_server.setsockopt(zmq.RCVHWM, self.config.max_requests)
        self.mq_server.setsockopt(zmq.SNDHWM, self.config.max_requests)
        self.mq_server.bind(self.config.mq_address)
        self._logger.debug(f"Server socket bound to {self.config.mq_address}")
        
        self.message_bus = MessageBus.instance()
        self.message_bus.start()
        
        self._running = True
        self._server_task = asyncio.create_task(self._run_server())
        self._logger.debug(f"Server task created: {self._server_task}")
        
        # 等待服务器真正启动
        await asyncio.sleep(0.1)
        
    async def stop(self):
        """停止服务端"""
        if not self._running:
            return
            
        self._logger.debug("Stopping server")
        self._running = False
        
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
                if not self.service:
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
                    self._logger.info("Published test response")
                    await self.message_bus.publish(
                        f"llm.{self.config.service_name}.{session_id}.complete",
                        {
                            "status": "complete",
                            "session_id": session_id,
                            "service": self.config.service_name
                        }
                    )
                    self._logger.info("Published completion notice")
                
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