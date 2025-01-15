import os
import zmq
import logging
import json
import time
import uuid
import asyncio
import threading

from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from urllib.parse import urlparse

from ..base.base_call import BaseCall
from ..base.async_service import AsyncService
from .message_bus import MessageBus
from .utils import normalize_address, init_bound_socket, cleanup_bound_socket, cleanup_connected_socket

class ReqRepService(BaseCall):
    """请求-响应服务"""

    def __init__(self, address: str = None, context: zmq.Context = None, logger: logging.Logger = None):
        """初始化服务
        
        Args:
            address: ZMQ地址，如果为None则自动生成
            context: ZMQ上下文，如果为None则创建新的
            logger: 日志记录器
        """
        super().__init__(logger)
        self._address = address or f"inproc://req.{self.__class__.__name__}.{id(self)}"
        self._context = context or zmq.Context.instance()
        self._rep_socket = None
        self._req_socket = None
        self._to_bind = True
        self._to_connect = True
        self._listen_task = None  # 用于存储监听任务
        self._request_counter = 0
        self._pending_tasks = {}

        if self._to_bind:
            self.init_rep()
        if self._to_connect:
            self.init_req()

    def init_rep(self):
        """同步初始化 REP 服务端"""
        if not self._to_bind:
            return
            
        self._logger.debug(f"Initializing REP service with context type: {type(self._context)}")
        
        # 使用同步 socket 进行通信
        if self._rep_socket is None:  # 避免重复创建
            self._rep_socket = self._context.socket(zmq.REP)
            self._logger.debug(f"Created REP socket type: {type(self._rep_socket)}")
            self._rep_socket.bind(self._address)
            self._logger.info(f"REP socket bound to {self._address}")
        
        try:
            loop = asyncio.get_running_loop()
            self._logger.debug("Found existing event loop")
            self._listen_task = loop.create_task(self._process_requests())
        except RuntimeError:
            self._logger.debug("No existing event loop, creating new one in thread")
            def run_async_loop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._process_requests())
                finally:
                    loop.close()
                    
            self._thread = threading.Thread(target=run_async_loop, daemon=True)
            self._thread.start()
            
        # 确保 REQ socket 只创建一次，并且只在需要时创建
        if self._req_socket is None and self._to_connect:
            self._req_socket = self._context.socket(zmq.REQ)
            self._logger.debug(f"Created REQ socket type: {type(self._req_socket)}")
            self._req_socket.connect(self._address)
            self._logger.info(f"Requester connected to: {self._address}")
            
        self._logger.info("REP service started")

    async def _process_requests(self):
        """后台处理请求的异步循环"""
        self._logger.debug("Starting request processing loop")
        poller = zmq.Poller()
        poller.register(self._rep_socket, zmq.POLLIN)
        
        while True:
            try:
                if self._rep_socket.closed:  # 检查 socket 是否已关闭
                    self._logger.warning("REP socket is closed, stopping processing loop")
                    break
                    
                events = dict(poller.poll(timeout=100))
                if self._rep_socket not in events:
                    await asyncio.sleep(0.01)
                    continue
                    
                # 使用 json 接收请求
                request_str = self._rep_socket.recv_string()
                self._logger.debug(f"Raw request string: {request_str!r}")
                request = json.loads(request_str)
                self._logger.debug(f"Parsed request: {request}")
                
                # 生成请求ID
                self._request_counter += 1
                request_id = f"REQ_{self._request_counter}"
                
                # 使用 json 返回响应
                response = {"request_id": request_id}
                response_str = json.dumps(response)
                self._logger.debug(f"Sending response: {response_str!r}")
                self._rep_socket.send_string(response_str)
                
                # 解析请求参数，确保正确的参数数量
                if isinstance(request, (tuple, list)):
                    args = [request]  # 将整个列表作为单个参数
                    kwargs = {}
                elif isinstance(request, dict):
                    args = ()
                    kwargs = request
                else:
                    args = (request,)
                    kwargs = {}
                    
                # 创建异步任务处理业务逻辑
                task = asyncio.create_task(
                    self.auto_call(
                        self.handle_request,
                        self.async_handle_request,
                        ReqRepService
                    )(*args, **kwargs)
                )
                
                self._pending_tasks[request_id] = task
                
                def done_callback(t, rid=request_id):
                    try:
                        result = t.result()
                        self._logger.debug(f"Task {rid} completed: {result}")
                    except Exception as e:
                        self._logger.error(f"Task {rid} failed: {e}", exc_info=True)
                    finally:
                        self._pending_tasks.pop(rid, None)
                        
                task.add_done_callback(done_callback)
                
            except Exception as e:
                if not self._rep_socket.closed:  # 只在 socket 未关闭时记录错误
                    self._logger.error(f"Error in request processing: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    def init_req(self):
        """初始化请求者"""
        if not self._to_connect:
            raise RuntimeError("Not in requester mode")

        self._req_socket = self._context.socket(zmq.REQ)
        self._req_socket.connect(self._address)
        self._logger.info(f"Requester connected to: {self._address}")

    def cleanup(self):
        """清理资源"""
        cleanup_bound_socket(self._rep_socket, self._address, self._logger)
        cleanup_connected_socket(self._req_socket, self._address, self._logger)
    
    async def handle_request(self, *args, **kwargs) -> Any:
        """服务端异步处理客户端请求"""
        raise NotImplementedError

    async def async_handle_request(self, *args, **kwargs) -> Any:
        """服务端异步处理客户端请求"""
        raise NotImplementedError

    def handle_call(self, *args, **kwargs) -> str:
        """同步客户端请求，返回请求ID"""
        if not self._to_connect or self._req_socket is None:
            raise RuntimeError("REQ socket not connected")
            
        # 构造请求
        if kwargs:
            request = kwargs
        elif len(args) > 1:
            request = args
        else:
            request = args[0] if args else None
            
        try:
            # 使用 json 发送请求
            request_str = json.dumps(request)
            self._logger.debug(f"Sending request string: {request_str!r}")
            self._req_socket.send_string(request_str)
            self._logger.debug(f"Request sent, waiting for response")
            
            # 使用 json 接收响应
            response_str = self._req_socket.recv_string()
            self._logger.debug(f"Raw response string: {response_str!r}")
            response = json.loads(response_str)
            self._logger.debug(f"Parsed response: {response}")
            
            if isinstance(response, dict) and "request_id" in response:
                return response["request_id"]
            else:
                raise RuntimeError(f"Invalid response from server: {response}")
        except Exception as e:
            self._logger.error(f"Error in handle_call: {e}", exc_info=True)
            self._logger.debug(f"Current socket state - REQ: {type(self._req_socket)}, REP: {type(self._rep_socket)}")
            raise

    def close(self):
        """关闭服务，清理资源"""
        if hasattr(self, '_listen_task') and self._listen_task:
            self._listen_task.cancel()
            
        if hasattr(self, '_thread') and self._thread:
            # 线程是 daemon 的，会自动退出
            self._thread = None
            
        if self._pending_tasks:
            for task in self._pending_tasks.values():
                task.cancel()
            
        # 先注销 poller
        if hasattr(self, '_poller'):
            self._poller = None
            
        # 然后关闭 sockets
        if self._rep_socket is not None:
            self._rep_socket.close(linger=0)  # 设置 linger=0 避免阻塞
            self._rep_socket = None
            
        if self._req_socket is not None:
            self._req_socket.close(linger=0)
            self._req_socket = None
