import os
import asyncio
import zmq.asyncio
import threading
import logging
import json
from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from urllib.parse import urlparse
import time
import tempfile
import hashlib
import async_timeout
from enum import Enum, auto

from ..async_utils import AsyncUtils
from .models import StreamingBlock, BlockType
from .utils import normalize_address, init_bound_socket, cleanup_bound_socket, cleanup_connected_socket

class BindState(Enum):
    """Socket绑定状态"""
    UNBOUND = auto()         # 未绑定
    LOCAL_BOUND = auto()     # 本地进程绑定
    EXTERNAL_BOUND = auto()  # 外部进程绑定
    REMOTE_BOUND = auto()    # 远程服务器绑定

class MessageBus:
    _bound_socket = None
    _bound_state = BindState.UNBOUND
    _bound_refs = 0
    _bound_lock = threading.Lock()
    
    def __init__(self, address=None, to_bind=True, to_connect=True, logger=None):
        self._logger = logger or logging.getLogger(__name__)
        self._async_utils = AsyncUtils(self._logger)
        self._logger.debug(f"MessageBus created with AsyncUtils: {id(self._async_utils)}")
        self._pub_socket = None
        self._sub_socket = None
        self._subscribed_topics = set()
        self._context = zmq.asyncio.Context.instance()
        self._is_publisher = False  # 标记是否使用了发布功能
        self._to_bind = to_bind
        self._to_connect = to_connect

        address = address or "inproc://message_bus"
        self._address = normalize_address(address)

        if to_bind:
            self.init_publisher()
        if to_connect:
            self.init_subscriber()
        
    @property
    def is_bound(self):
        return self._bound_socket is not None

    @property
    def is_connected(self):
        return self._sub_socket is not None

    @property
    def is_bound_outside(self):
        """检查是否被外部进程绑定"""
        return MessageBus._bound_state in (BindState.EXTERNAL_BOUND, BindState.REMOTE_BOUND)

    def init_publisher(self):
        """尝试绑定socket，处理已存在的情况"""
        if not self._to_bind:
            raise RuntimeError("Not in publisher mode")
        
        with MessageBus._bound_lock:
            self._logger.debug(f"Initializing publisher for {self._address}, current refs: {MessageBus._bound_refs}")
            
            parsed = urlparse(self._address)
            is_local = parsed.scheme == 'inproc' or (
                parsed.scheme in ('tcp', 'ipc') and 
                (parsed.hostname in ('localhost', '127.0.0.1', None))
            )
            
            if MessageBus._bound_socket is not None:
                if is_local and MessageBus._bound_state == BindState.LOCAL_BOUND:
                    # 本地已绑定，增加引用计数
                    if not self._is_publisher:  # 只有第一次初始化时增加引用计数
                        MessageBus._bound_refs += 1
                        self._is_publisher = True
                    self._pub_socket = MessageBus._bound_socket
                else:
                    # 外部或远程绑定
                    self._pub_socket = None
                    self._is_publisher = True
                
                self._logger.info(f"Address {self._address} already bound, state: {MessageBus._bound_state.name}, refs: {MessageBus._bound_refs if is_local else 'N/A'}")
                return
            
            # 尝试绑定新socket
            already_bound, socket_result = init_bound_socket(self._context, zmq.PUB, self._address, self._logger)
            if already_bound:
                # 外部已绑定
                MessageBus._bound_state = BindState.EXTERNAL_BOUND
                self._pub_socket = None
                self._is_publisher = True
                self._logger.debug(f"Socket already bound externally")
                return
            else:
                if is_local:
                    # 本地新绑定
                    MessageBus._bound_socket = socket_result
                    MessageBus._bound_state = BindState.LOCAL_BOUND
                    MessageBus._bound_refs = 1
                    self._pub_socket = socket_result
                    self._is_publisher = True
                else:
                    # 远程新绑定
                    MessageBus._bound_state = BindState.REMOTE_BOUND
                    self._pub_socket = socket_result
                    self._is_publisher = True
                
            MessageBus._bound_address = self._address
            self._logger.debug(f"Socket bound with state: {MessageBus._bound_state.name}, refs: {MessageBus._bound_refs if is_local else 'N/A'}")

    def init_subscriber(self):
        """初始化订阅者"""
        if not self._to_connect:
            raise RuntimeError("Not in subscriber mode")

        self._sub_socket = self._context.socket(zmq.SUB)
        self._sub_socket.connect(self._address)
        self._logger.info(f"Subscriber connected to: {self._address}")

    def publish(self, topic: str, message: Union[dict, str, StreamingBlock]=None, end: bool = False, delay: float = 0.01):
        """发布消息，如果存在订阅套接字则自动订阅"""
        if not isinstance(topic, str):
            raise ValueError("Topic must be a string")
        if not self._bound_socket:
            raise RuntimeError("No bound socket found")

        if message:
            if isinstance(message, str):
                message = StreamingBlock(block_type=BlockType.CHUNK, content=message)
            elif isinstance(message, dict):
                message = StreamingBlock(**message)
            
            if not isinstance(message, StreamingBlock):
                raise ValueError("Message must be a StreamingBlock, a string or a dict")

        try:
            # 如果存在订阅套接字，确保已订阅该主题
            if self._sub_socket and topic not in self._subscribed_topics:
                self._sub_socket.subscribe(topic.encode())
                self._subscribed_topics.add(topic)
                self._logger.debug(f"Auto-subscribed to topic: {topic}")
                # 添加短暂延迟，确保订阅生效
                time.sleep(delay)

            if message:
                # 使用multipart发送消息
                self._bound_socket.send_multipart([
                    topic.encode(),
                    json.dumps(message.model_dump()).encode()
                ])
                self._logger.debug(f"Published to {topic}: {message}")
            else:
                end = True

            if end and not (message and message.block_type == BlockType.END):
                end_block = StreamingBlock(block_type=BlockType.END, content="done")
                self._bound_socket.send_multipart([
                    topic.encode(),
                    json.dumps(end_block.model_dump()).encode()
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

    def subscribe(self, topics: Union[str, List[str]], delay: float = 0.01):
        """仅完成主题订阅，不收取消息"""
        if not self._sub_socket:
            raise RuntimeError("Not in subscriber mode")

        topics = [topics] if isinstance(topics, str) else topics
        if any(not isinstance(topic, str) for topic in topics):
            raise ValueError("All topics must be strings")

        try:            
            for topic in topics:
                if topic not in self._subscribed_topics:
                    self._sub_socket.subscribe(topic.encode())
                    self._logger.debug(f"Subscribed to topic: {topic}")
                    self._subscribed_topics.add(topic)
                    
            # 添加短暂延迟，确保订阅生效
            time.sleep(delay)

        except Exception as e:
            self._logger.error(f"Subscription error: {e}")
            raise

    def __del__(self):
        """析构函数确保资源被清理"""
        try:
            # 如果事件循环还在运行，尝试正常清理
            if asyncio.get_event_loop().is_running():
                self.cleanup()
            else:
                # 事件循环已关闭，执行同步清理
                if self._sub_socket:
                    cleanup_connected_socket(self._sub_socket, self._address, self._logger)
                    self._sub_socket = None
                if self._pub_socket:
                    cleanup_bound_socket(self._pub_socket, self._address, self._logger)
                    self._pub_socket = None
        except Exception as e:
            # 在对象销毁时不抛出异常
            if self._logger:
                self._logger.warning(f"Error during MessageBus cleanup: {e}")

    def cleanup(self):
        """清理资源"""
        if self._is_publisher:
            parsed = urlparse(self._address)
            is_local = parsed.scheme == 'inproc' or (
                parsed.scheme in ('tcp', 'ipc') and 
                (parsed.hostname in ('localhost', '127.0.0.1', None))
            )
            
            with MessageBus._bound_lock:
                if is_local and MessageBus._bound_state == BindState.LOCAL_BOUND:
                    self._logger.debug(f"Cleaning up local publisher for {self._address}, current refs: {MessageBus._bound_refs}")
                    if MessageBus._bound_refs > 0:
                        MessageBus._bound_refs -= 1
                        self._logger.debug(f"Decreased bound socket refs to: {MessageBus._bound_refs}")
                        
                        if MessageBus._bound_refs == 0:
                            if MessageBus._bound_socket:
                                self._logger.info("Cleaning up bound socket (last reference)")
                                socket_to_clean = MessageBus._bound_socket
                                MessageBus._bound_socket = None
                                MessageBus._bound_state = BindState.UNBOUND
                                MessageBus._bound_address = None
                                cleanup_bound_socket(socket_to_clean, self._address, self._logger)
                        else:
                            self._logger.debug(f"Skipping bound socket cleanup, remaining refs: {MessageBus._bound_refs}")
                elif self._pub_socket:
                    # 远程连接直接清理自己的socket
                    cleanup_bound_socket(self._pub_socket, self._address, self._logger)
        
        # 清理订阅socket
        if self._sub_socket:
            cleanup_connected_socket(self._sub_socket, self._address, self._logger)
            self._sub_socket = None
            self._logger.debug(f"Cleaned up subscriber for {self._address}")

    async def async_collect(self, timeout: float = None, once: bool = True) -> AsyncGenerator[StreamingBlock, None]:
        """异步收集消息直到收到结束标记或超时"""
        self._logger.debug(f"async_collect started for topics: {self._subscribed_topics}")
        
        if not self._sub_socket:
            raise RuntimeError("Not in subscriber mode")

        if not self._subscribed_topics:
            raise RuntimeError("No topics subscribed")

        collect_start = time.time()
        last_poll = time.time()
        poll_interval = 0.01  # 10ms
        
        # 保存当前任务引用
        self._current_collection_task = asyncio.current_task()
        self._logger.debug(f"Collection task created: {self._current_collection_task.get_name()}")
        
        try:
            while True:
                try:
                    current_time = time.time()
                    remaining_timeout = None
                    if timeout:
                        elapsed = current_time - collect_start
                        if elapsed >= timeout:
                            break
                        remaining_timeout = min(timeout - elapsed, poll_interval)
                    else:
                        remaining_timeout = poll_interval
                    
                    if await self._sub_socket.poll(timeout=remaining_timeout * 1000):
                        [topic_bytes, payload] = await self._sub_socket.recv_multipart()
                        message = json.loads(payload.decode())
                        message['topic'] = topic_bytes.decode()
                        
                        # 转换为 StreamingBlock
                        block = StreamingBlock(**message)
                        self._logger.debug(f"Yielding message: {block}")
                        yield block
                        
                        if block.block_type == BlockType.END and once:
                            break
                    
                    last_poll = current_time
                    
                except Exception as e:
                    self._logger.error(f"Collection error: {e}")
                    raise
                
        except GeneratorExit:
            self._logger.debug(f"Generator {self._current_collection_task.get_name()} closing")
        except asyncio.CancelledError:
            self._logger.debug(f"Task {self._current_collection_task.get_name()} cancelled")
            raise
        finally:
            self._logger.debug(f"Collection task {self._current_collection_task.get_name()} finished")
            if hasattr(self, '_current_collection_task'):
                self._current_collection_task = None

    def collect(self, timeout: float = None, once: bool = True) -> Generator[StreamingBlock, None, None]:
        """同步收集消息"""
        return self._async_utils.wrap_async_generator(
            self.async_collect(timeout=timeout, once=once)
        )
