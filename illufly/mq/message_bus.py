import os
import zmq.asyncio
import threading
import logging
import json
from typing import List, AsyncIterator, Dict, Any
from .utils import get_ipc_path
import asyncio

class MessageBus:
    """全局消息总线 - 利用 ZMQ 端口绑定特性实现单例"""
    _instance = None
    _context = None
    _pub_socket = None
    _lock = threading.Lock()
    _started = False
    _is_server = False
    _address = None

    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(__name__)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def instance(cls, name: str = "message_bus"):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = cls()
                    instance._address = get_ipc_path(name)
                    logging.debug(f"Instance initialized with address: {instance._address}")
        return cls._instance
    
    def start(self):
        """启动消息总线（如果尚未启动）"""
        with self._lock:
            if not self._started:
                try:
                    self._context = zmq.asyncio.Context.instance()
                    self._pub_socket = self._context.socket(zmq.PUB)
                    self._pub_socket.setsockopt(zmq.SNDHWM, 1000)
                    self._pub_socket.setsockopt(zmq.RCVHWM, 1000)
                    self._pub_socket.setsockopt(zmq.LINGER, 0)
                    self._pub_socket.bind(self._address)
                    self._started = True
                    self._is_server = True
                    self._logger.info(f"Global message bus started at {self._address} with HWM=1000")
                except zmq.error.ZMQError as e:
                    self._logger.info("Message bus already running, connecting as client")
                    self._pub_socket.connect(self._address)
                    self._started = True
                    self._is_server = False

    async def publish(self, topic: str, message: Dict[str, Any]):
        """发布消息到指定主题"""
        if not self._started:
            raise RuntimeError("Message bus not started")
            
        if not self._pub_socket:
            raise RuntimeError("Publisher socket not initialized")
            
        try:
            self._logger.debug(f"Publishing to {topic}: {message}")
            await self._pub_socket.send_multipart([
                topic.encode(),
                json.dumps(message).encode()
            ])
            self._logger.debug("Message published")
        except Exception as e:
            self._logger.error(f"Error publishing message: {e}")
            raise

    async def subscribe(self, topics: List[str]) -> AsyncIterator[Dict[str, Any]]:
        """订阅指定主题的消息流"""
        if not self._started:
            raise RuntimeError("Message bus not started")
            
        self._logger.debug(f"Creating subscription for topics: {topics}")
        sub_socket = self._context.socket(zmq.SUB)
        sub_socket.setsockopt(zmq.RCVHWM, 1000)
        sub_socket.connect(self._address)
        
        try:
            # 订阅所有指定的主题
            for topic in topics:
                self._logger.debug(f"Subscribing to topic: {topic}")
                sub_socket.setsockopt(zmq.SUBSCRIBE, topic.encode())
            
            # 等待订阅生效
            await asyncio.sleep(0.1)
                
            while True:
                try:
                    self._logger.debug("Waiting for message...")
                    [topic, message] = await sub_socket.recv_multipart()
                    topic = topic.decode()
                    message = json.loads(message.decode())
                    self._logger.debug(f"Received message on {topic}: {message}")
                    yield message
                except asyncio.CancelledError:
                    self._logger.debug("Subscription cancelled")
                    break
                except Exception as e:
                    self._logger.error(f"Error receiving message: {e}")
                    raise
                    
        finally:
            self._logger.debug("Closing subscription socket")
            sub_socket.close(linger=0)

    @property
    def address(self) -> str:
        return self._address
    
    @property
    def socket(self):
        if not self._started:
            raise RuntimeError("Message bus not started")
        return self._pub_socket
    
    def __del__(self):
        self.cleanup()
    
    @classmethod
    def release(cls):
        logging.debug("MessageBus.release called")
        with cls._lock:
            if cls._instance:
                logging.debug(f"Releasing MessageBus instance (is_server={cls._instance._is_server})")
                if not cls._instance._is_server:
                    if cls._instance._pub_socket:
                        logging.debug("Closing client socket")
                        cls._instance._pub_socket.close(linger=0)
                        cls._instance._pub_socket = None
                    cls._instance = None
                    cls._started = False
                    logging.info("Message bus client released")
                else:
                    if cls._instance._pub_socket:
                        logging.debug("Closing server socket")
                        cls._instance._pub_socket.close(linger=0)
                        cls._instance._pub_socket = None
                    logging.debug("Starting cleanup")
                    cls._instance.cleanup()
                    cls._instance = None
                    cls._started = False
                    logging.info("Message bus server released")
            else:
                logging.debug("No MessageBus instance to release")

    def cleanup(self):
        if self._address and self._address.startswith("ipc://"):
            ipc_file = self._address[6:]
            if os.path.exists(ipc_file):
                try:
                    logging.debug(f"Attempting to remove IPC file: {ipc_file}")
                    os.remove(ipc_file)
                    logging.info(f"Cleaned up IPC file: {ipc_file}")
                except OSError as e:
                    logging.warning(f"Failed to clean up IPC file: {e}")
            else:
                logging.debug(f"No IPC file to clean up or file doesn't exist: {ipc_file}") 

    async def ensure_subscription_ready(self, topic: str, timeout: float = 1.0) -> bool:
        """确保订阅已经准备就绪
        
        Args:
            topic: 要测试的主题
            timeout: 超时时间（秒）
            
        Returns:
            bool: 订阅是否就绪
        """
        test_message = {"test": True}
        try:
            # 发送测试消息
            await self.publish(f"test.{topic}", test_message)
            
            # 创建测试订阅
            async with asyncio.timeout(timeout):
                async for msg in self.subscribe([f"test.{topic}"]):
                    if msg == test_message:
                        return True
                        
        except Exception as e:
            logger.warning(f"Subscription test failed: {e}")
            return False
            
        return False 