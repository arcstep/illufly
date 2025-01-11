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
        self._logger = logger or logging.getLogger(config.service_name)
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
                    self._logger.debug("Waiting for request...")
                    request = await asyncio.wait_for(
                        self.mq_server.recv_json(),
                        timeout=0.5
                    )
                    self._logger.debug(f"Received request: {request}")
                    
                    session_id = request.get("session_id")
                    prompt = request.get("prompt")
                    kwargs = request.get("kwargs", {})
                    
                    try:
                        # 处理请求并等待完成
                        self._logger.debug(f"Processing request for session {session_id}")
                        await self._handle_request(prompt, session_id, kwargs)
                        
                        # 处理成功后发送成功响应
                        self._logger.debug(f"Sending success response for session {session_id}")
                        await self.mq_server.send_json({
                            "status": "success",
                            "session_id": session_id
                        })
                    except Exception as e:
                        # 处理失败时发送错误响应
                        self._logger.error(f"Error processing request: {e}")
                        await self.mq_server.send_json({
                            "status": "error",
                            "session_id": session_id,
                            "error": str(e)
                        })
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self._logger.error(f"Server error: {e}")
                    if not self._running:
                        break
                    
        except asyncio.CancelledError:
            self._logger.info("Server loop cancelled")
            raise
        finally:
            self._logger.info("Server loop ended")

    async def _handle_request(self, prompt: str, session_id: str, kwargs: dict):
        """处理单个请求并发布结果"""
        self._logger.debug(f"Starting request handler for session {session_id}")
        try:
            # 输入验证
            if prompt is None:
                raise ValueError("Prompt cannot be None")
            
            if not isinstance(prompt, str):
                raise TypeError(f"Prompt must be string, got {type(prompt)}")
            
            if not prompt.strip():
                raise ValueError("Prompt cannot be empty")
            
            if not self.service:
                self._logger.debug("No service instance, sending test response")
                await self.message_bus.publish(
                    f"llm.{self.config.service_name}.{session_id}",
                    {
                        "session_id": session_id,
                        "service": self.config.service_name,
                        "content": f"Test response for: {prompt}"
                    }
                )
                await self.message_bus.publish(
                    f"llm.{self.config.service_name}.{session_id}.complete",
                    {
                        "status": "complete",
                        "session_id": session_id,
                        "service": self.config.service_name
                    }
                )
                return
            
            # 处理实际服务请求
            async for event in self.service.process_request(prompt, **kwargs):
                event_dict = event.model_dump()
                event_dict["session_id"] = session_id
                event_dict["service"] = self.config.service_name
                await self.message_bus.publish(
                    f"llm.{self.config.service_name}.{session_id}",
                    event_dict
                )
            
            # 发送完成通知
            await self.message_bus.publish(
                f"llm.{self.config.service_name}.{session_id}.complete",
                {
                    "status": "complete",
                    "session_id": session_id,
                    "service": self.config.service_name
                }
            )
                
        except Exception as e:
            self._logger.error(f"Error handling request: {e}")
            # 发送错误通知
            await self.message_bus.publish(
                f"llm.{self.config.service_name}.{session_id}.error",
                {
                    "error": str(e),
                    "session_id": session_id,
                    "service": self.config.service_name
                }
            )
            # 发送错误响应
            raise 