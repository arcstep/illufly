import os
import asyncio
import zmq.asyncio
import threading
import logging
import json
from enum import Enum
from typing import List, AsyncIterator, Dict, Any
from ..envir import get_env
from .utils import get_ipc_path

class MessageBusType(Enum):
    INPROC = "inproc"
    IPC = "ipc"
    TCP = "tcp"

class MessageBusBase:
    """消息总线基类"""
    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(__name__)
        self._context = None
        self._pub_socket = None
        self._started = False
        self._address = None

    async def publish(self, topic: str, message: Dict[str, Any]):
        """发布消息到指定主题 - 基类要求显式启动"""
        if not self._started:
            raise RuntimeError("Message bus not started")
            
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

    def subscribe(self, topics: List[str]) -> AsyncIterator[Dict[str, Any]]:
        """订阅指定主题的消息流 - 返回异步迭代器"""
        if not self._started:
            raise RuntimeError("Message bus not started")
            
        self._logger.debug(f"Creating subscription for topics: {topics}")
        sub_socket = self._context.socket(zmq.SUB)
        sub_socket.setsockopt(zmq.RCVHWM, 1000)
        sub_socket.connect(self._address)
        
        for topic in topics:
            self._logger.debug(f"Subscribing to topic: {topic}")
            sub_socket.setsockopt(zmq.SUBSCRIBE, topic.encode())

        class MessageIterator:
            def __init__(self, socket, logger):
                self.socket = socket
                self.logger = logger

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    [topic, message] = await self.socket.recv_multipart()
                    topic = topic.decode()
                    message = json.loads(message.decode())
                    self.logger.debug(f"Received message on {topic}: {message}")
                    return message
                except asyncio.CancelledError:
                    self.socket.close(linger=0)
                    raise StopAsyncIteration
                except Exception as e:
                    self.logger.error(f"Error receiving message: {e}")
                    self.socket.close(linger=0)
                    raise

        return MessageIterator(sub_socket, self._logger)

    @property
    def address(self) -> str:
        return self._address

    def cleanup(self):
        if self._pub_socket:
            self._pub_socket.close(linger=0)
            self._pub_socket = None
        self._started = False

class InprocMessageBus(MessageBusBase):
    """进程内消息总线 - 支持自启动的单例模式"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, logger=None):
        if not hasattr(self, '_initialized'):
            super().__init__(logger)
            self._address = "inproc://message_bus"
            self._initialized = True
            self._logger.debug(f"InprocMessageBus initialized, id: {id(self)}")

    def _ensure_started(self):
        """确保消息总线已启动"""
        with self._lock:
            if not self._started:
                self._context = zmq.asyncio.Context.instance()
                self._pub_socket = self._context.socket(zmq.PUB)
                self._pub_socket.bind(self._address)
                self._started = True
                self._logger.info(f"Inproc message bus started at {self._address}")

    async def publish(self, topic: str, message: Dict[str, Any]):
        """重写publish方法以支持自启动"""
        self._ensure_started()
        await super().publish(topic, message)

    def subscribe(self, topics: List[str]) -> AsyncIterator[Dict[str, Any]]:
        """重写subscribe方法以支持自启动"""
        self._ensure_started()
        return super().subscribe(topics)  # 直接返回异步迭代器

class DistributedMessageBus(MessageBusBase):
    """分布式消息总线基类 - 需要显式启动"""
    def __init__(self, address: str, role: str = "client", logger=None):
        if not role in ("server", "client"):
            raise ValueError("Role must be either 'server' or 'client'")
        super().__init__(logger)
        self._address = address
        self._role = role
        self._is_server = role == "server"

    def start(self):
        """启动分布式消息总线"""
        if not self._started:
            self._context = zmq.asyncio.Context.instance()
            self._pub_socket = self._context.socket(zmq.PUB)
            self._pub_socket.setsockopt(zmq.SNDHWM, 1000)
            self._pub_socket.setsockopt(zmq.RCVHWM, 1000)
            self._pub_socket.setsockopt(zmq.LINGER, 0)
            
            if self._is_server:
                self._pub_socket.bind(self._address)
                self._logger.info(f"Distributed message bus server started at {self._address}")
            else:
                self._pub_socket.connect(self._address)
                self._logger.info(f"Connected to message bus at {self._address}")
            
            self._started = True

class IpcMessageBus(DistributedMessageBus):
    """IPC 消息总线实现"""
    def __init__(self, path: str = None, role: str = "client", logger=None):
        path = path or get_ipc_path("message_bus")
        address = f"ipc://{path}"
        super().__init__(address, role, logger)

    def cleanup(self):
        super().cleanup()
        if self._is_server and self._address.startswith("ipc://"):
            ipc_file = self._address[6:]
            if os.path.exists(ipc_file):
                try:
                    os.remove(ipc_file)
                    self._logger.info(f"Cleaned up IPC file: {ipc_file}")
                except OSError as e:
                    self._logger.warning(f"Failed to clean up IPC file: {e}")

class TcpMessageBus(DistributedMessageBus):
    """TCP 消息总线实现"""
    def __init__(self, host: str, port: int, role: str = "client", logger=None):
        address = f"tcp://{host}:{port}"
        super().__init__(address, role, logger)

def create_message_bus(bus_type: MessageBusType, **kwargs) -> MessageBusBase:
    """消息总线工厂方法"""
    if bus_type == MessageBusType.INPROC:
        return InprocMessageBus(**kwargs)
    elif bus_type == MessageBusType.IPC:
        return IpcMessageBus(**kwargs)
    elif bus_type == MessageBusType.TCP:
        return TcpMessageBus(**kwargs)
    else:
        raise ValueError(f"Unsupported message bus type: {bus_type}") 