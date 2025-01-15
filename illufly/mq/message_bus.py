import os
import asyncio
import zmq
import threading
import logging
import json
from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from urllib.parse import urlparse
import time
import tempfile
import hashlib
import async_timeout

from ..base.async_service import AsyncService
from .utils import normalize_address, init_bound_socket, cleanup_bound_socket, cleanup_connected_socket

class MessageBus:
    _bound_socket = None
    _bound_address = None
    _bound_lock = threading.Lock()
    
    def __init__(self, address="inproc://message_bus", to_bind=True, to_connect=True, logger=None):
        self._logger = logger or logging.getLogger(__name__)
        self._pub_socket = None
        self._sub_socket = None
        self._subscribed_topics = set()
        self._context = zmq.asyncio.Context.instance()

        self._address = normalize_address(address)  # 规范化地址

        if to_bind:
            self._to_bind = True
            self.init_publisher()
        if to_connect:
            self._to_connect = True
            self.init_subscriber()
        
    @property
    def is_bound(self):
        return self._bound_socket is not None

    @property
    def is_connected(self):
        return self._sub_socket is not None

    @property
    def is_bound_outside(self):
        return MessageBus._bound_socket is True

    def init_publisher(self):
        """尝试绑定socket，处理已存在的情况"""
        if not self._to_bind:
            raise RuntimeError("Not in publisher mode")
        
        with MessageBus._bound_lock:
            # 检查是否已有绑定的socket
            if MessageBus._bound_socket:
                self._logger.info(f"Address {self._address} already bound")
                return                
            already_bound, socket_result = init_bound_socket(self._context, zmq.PUB, self._address, self._logger)
            if already_bound is True:
                MessageBus._bound_socket = True
                return
            else:
                MessageBus._bound_socket = socket_result
                self._pub_socket = socket_result
            MessageBus._bound_address = self._address

    def init_subscriber(self):
        """初始化订阅者"""
        if not self._to_connect:
            raise RuntimeError("Not in subscriber mode")

        self._sub_socket = self._context.socket(zmq.SUB)
        self._sub_socket.connect(self._address)
        self._logger.info(f"Subscriber connected to: {self._address}")

    def publish(self, topic: str, message: Union[dict, str]=None, end: bool = False):
        """发布消息，如果存在订阅套接字则自动订阅"""
        if not isinstance(topic, str):
            raise ValueError("Topic must be a string")
        if not self._bound_socket:
            raise RuntimeError("Not in publisher mode")

        if message and isinstance(message, str):
            message = {"content": message}

        try:
            # 如果存在订阅套接字，确保已订阅该主题
            if self._sub_socket and topic not in self._subscribed_topics:
                self._sub_socket.subscribe(topic.encode())
                self._subscribed_topics.add(topic)
                self._logger.debug(f"Auto-subscribed to topic: {topic}")
                time.sleep(0.01)
            if message:
                # 使用multipart发送消息
                self._bound_socket.send_multipart([
                    topic.encode(),
                    json.dumps(message).encode()
                ])
                self._logger.debug(f"Published to {topic}: {message}")
            else:
                end = True

            if end:
                end_block = {"block_type": "end"}
                self._bound_socket.send_multipart([
                    topic.encode(),
                    json.dumps(end_block).encode()
                ])

        except Exception as e:
            self._logger.error(f"Publish failed: {e}")
            raise

    def unsubscribe(self, topics: Union[str, List[str]]=""):
        """取消订阅"""
        if self._sub_socket:
            topics = [topics] if isinstance(topics, str) else topics
            for topic in topics:
                self._sub_socket.unsubscribe(topic.encode())
            self._logger.debug(f"Unsubscribed from topic: {topic}")

    def subscribe(self, topics: Union[str, List[str]]):
        """仅完成主题订阅，不收取消息"""

        topics = [topics] if isinstance(topics, str) else topics
        if any(not isinstance(topic, str) for topic in topics):
            raise ValueError("All topics must be strings")

        try:            
            for topic in topics:
                if topic not in self._subscribed_topics:
                    self._sub_socket.subscribe(topic.encode())
                    self._logger.debug(f"Subscribed to topic: {topic}")
                    self._subscribed_topics.add(topic)                

        except Exception as e:
            self._logger.error(f"Subscription error: {e}")
            raise

    def cleanup(self):
        """清理资源"""
        if self._pub_socket:
            # 如果是绑定者，清理静态变量
            if self._pub_socket is MessageBus._bound_socket:
                MessageBus._bound_socket = None
                MessageBus._bound_address = None
        cleanup_bound_socket(self._pub_socket, self._address, self._logger)
        cleanup_connected_socket(self._sub_socket, self._address, self._logger)

    async def collect_async(self, once: bool = True, timeout: float = None) -> AsyncGenerator[dict, None]:
        """异步收集消息直到收到结束标记或超时
        
        Args:
            once: 是否只收集一次
            timeout: 每次接收消息的超时时间（秒），None表示永不超时
        """
        if not self._sub_socket:
            raise RuntimeError("Not in subscriber mode")
        
        if not self._subscribed_topics:
            raise RuntimeError("No topics subscribed")
        
        try:
            while True:
                try:
                    if timeout is not None:
                        async with async_timeout.timeout(timeout):
                            [topic, payload] = await self._sub_socket.recv_multipart()
                    else:
                        [topic, payload] = await self._sub_socket.recv_multipart()                        
                    message = json.loads(payload.decode())
                    message['topic'] = topic.decode()                    
                    yield message
                    # 检查是否结束
                    if once and message.get('block_type') == 'end':
                        break
                except asyncio.TimeoutError:
                    self._logger.debug(f"Message receive timeout after {timeout}s")
                    break
                except StopAsyncIteration:
                    break
        except Exception as e:
            self._logger.error(f"Collection error: {e}")
            raise

    def collect(self, once: bool = True, timeout: float = 30.0) -> Generator[dict, None, None]:
        """同步收集消息
        
        Args:
            once: 是否只收集一次
            timeout: 超时时间（秒）
            
        Yields:
            dict: 收到的消息
        """
        return AsyncService(self._logger).wrap_async_generator(
            self.collect_async(once=once, timeout=timeout)
        )
