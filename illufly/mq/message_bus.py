import os
import asyncio
import zmq.asyncio
import threading
import logging
import json
from typing import List, AsyncIterator, Dict, Any, Optional
from enum import Enum
from urllib.parse import urlparse
import time
import tempfile
from pathlib import Path
import hashlib

class MessageBus:
    _bound_socket = None
    _bound_address = None
    _bound_lock = threading.Lock()
    
    def __init__(self, address="inproc://message_bus", logger=None):
        self._logger = logger or logging.getLogger(__name__)
        self._pub_socket = None
        self._sub_socket = None
        self._context = zmq.asyncio.Context.instance()

        self._address = self._normalize_address(address)  # 规范化地址
        self._is_inproc = self._address.startswith("inproc://")
        self._is_ipc = self._address.startswith("ipc://")
        
        self._try_bind()
        self._init_subscriber()
            
    def _normalize_address(self, address: str) -> str:
        """规范化地址格式，处理IPC地址长度限制"""
        if address.startswith("ipc://"):
            # 解析IPC路径
            path = urlparse(address).path
            if not path:
                # 如果没有指定路径，使用临时目录
                path = os.path.join(tempfile.gettempdir(), "message_bus.ipc")
                
            # 计算最大允许长度（保留20字符给zmq内部使用）
            max_path_length = 87
            if len(path) > max_path_length:
                # 使用hash处理超长路径
                dir_path = os.path.dirname(path)
                file_name = os.path.basename(path)
                hashed_name = hashlib.md5(file_name.encode()).hexdigest()[:10] + ".ipc"
                
                # 如果目录路径也太长，使用临时目录
                if len(dir_path) > (max_path_length - len(hashed_name) - 1):
                    dir_path = tempfile.gettempdir()
                    
                path = os.path.join(dir_path, hashed_name)
                self._logger.warning(
                    f"IPC path too long, truncated to: {path}"
                )
            
            # 确保目录存在
            # os.makedirs(os.path.dirname(path), exist_ok=True)
            return f"ipc://{path}"
            
        return address
        
    def _try_bind(self):
        """尝试绑定socket，处理已存在的情况"""
        with MessageBus._bound_lock:
            # 检查是否已有绑定的socket
            if MessageBus._bound_socket:
                self._logger.warning(f"Address {self._address} already bound")
                return
                
            try:
                self._pub_socket = self._context.socket(zmq.PUB)
                self._pub_socket.bind(self._address)
                MessageBus._bound_socket = self._pub_socket
                self._logger.info(f"Publisher bound to: {self._address}")
                
            except zmq.ZMQError as e:
                if e.errno == zmq.EADDRINUSE:
                    self._logger.warning(f"Address {self._address} in use by another process")
                    if self._is_inproc:
                        MessageBus._bound_socket = True  # 标记为已绑定
                    self._init_subscriber()
                else:
                    raise
            
    def _init_subscriber(self):
        """初始化订阅者"""
        self._sub_socket = self._context.socket(zmq.SUB)
        self._sub_socket.connect(self._address)
        self._logger.info(f"Subscriber connected to: {self._address}")

    def publish(self, topic: str, message: dict):
        """发布消息"""
        if not self._bound_socket:
            raise RuntimeError("Not in publisher mode")
            
        try:
            # 使用multipart发送消息
            self._bound_socket.send_multipart([
                topic.encode(),
                json.dumps(message).encode()
            ])
            self._logger.debug(f"Published to {topic}: {message}")
        except Exception as e:
            self._logger.error(f"Publish failed: {e}")
            raise

    async def subscribe(self, topics: list):
        """订阅消息"""
        if not self._sub_socket:
            raise RuntimeError("Not in subscriber mode")
            
        try:
            # 先取消所有订阅（除了心跳）
            self._sub_socket.unsubscribe(b"")  # 取消所有订阅
            
            # 设置新的订阅主题
            for topic in topics:
                self._sub_socket.subscribe(topic.encode())
                self._logger.debug(f"Subscribed to topic: {topic}")
                
            while True:
                [topic, payload] = await self._sub_socket.recv_multipart()
                message = json.loads(payload.decode())
                message['topic'] = topic.decode()
                
                self._logger.debug(f"Received message on {topic.decode()}: {message}")
                yield message
                
        except asyncio.CancelledError:
            self._logger.debug("Subscribe operation cancelled")
            raise
        except Exception as e:
            self._logger.error(f"Subscription error: {e}")
            raise

    def cleanup(self):
        """清理资源"""
        if self._pub_socket:
            self._pub_socket.close()
            # 如果是绑定者，清理静态变量
            if self._pub_socket is MessageBus._bound_socket:
                MessageBus._bound_socket = None
                MessageBus._bound_address = None
            # 如果是IPC，删除文件
            if self._is_ipc:
                try:
                    path = urlparse(self._address).path
                    if os.path.exists(path):
                        os.unlink(path)
                except Exception as e:
                    self._logger.warning(f"Failed to remove IPC file: {e}")
            self._pub_socket = None
            
        if self._sub_socket:
            self._sub_socket.close()
            self._sub_socket = None
            
        self._logger.info("MessageBus cleaned up")

