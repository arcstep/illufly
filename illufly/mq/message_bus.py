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

class MessageBus:
    _bound_socket = None  # 类变量，跟踪已绑定的socket
    _bound_lock = threading.Lock()  # 保护绑定操作的锁
    
    def __init__(self, address="inproc://message_bus", role="publisher", logger=None):
        self._address = address
        self._role = role
        self._logger = logger or logging.getLogger(__name__)
        self._pub_socket = None
        self._sub_socket = None
        self._context = zmq.asyncio.Context.instance()
        self._heartbeat_task = None
        self._is_inproc = address.startswith("inproc://")
        self._ready = asyncio.Event()  # 用于标记初始化完成
        
        # 在构造函数中只做基本初始化
        if role == "publisher":
            self._try_bind()
        else:
            self._init_subscriber()
            
    def _try_bind(self):
        """尝试绑定socket，处理已存在的情况"""
        with MessageBus._bound_lock:
            # 检查是否已有绑定的socket（仅对inproc地址）
            if self._is_inproc and MessageBus._bound_socket:
                self._logger.warning(f"Address {self._address} already bound, switching to subscriber mode")
                self._role = "subscriber"
                self._init_subscriber()
                return
                
            try:
                self._pub_socket = self._context.socket(zmq.PUB)
                self._pub_socket.bind(self._address)
                if self._is_inproc:
                    MessageBus._bound_socket = self._pub_socket
                self._logger.info(f"Publisher bound to: {self._address}")
                
            except zmq.ZMQError as e:
                if e.errno == zmq.EADDRINUSE:
                    self._logger.warning(f"Address {self._address} in use, switching to subscriber mode")
                    if self._is_inproc:
                        MessageBus._bound_socket = True  # 标记为已绑定
                    self._role = "subscriber"
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
        if not self._pub_socket:
            raise RuntimeError("Not in publisher mode")
            
        try:
            # 使用multipart发送消息
            self._pub_socket.send_multipart([
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
            while True:
                # 使用 recv_multipart 接收多部分消息
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
            self._pub_socket = None
            
        if self._sub_socket:
            self._sub_socket.close()
            self._sub_socket = None
            
        self._logger.info("MessageBus cleaned up")

