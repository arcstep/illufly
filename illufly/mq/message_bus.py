import os
import asyncio
import zmq.asyncio
import threading
import logging
import json
from typing import List, Union, Dict, Any, Optional
from urllib.parse import urlparse
import time
import tempfile
import hashlib
import async_timeout

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

        self._address = self._normalize_address(address)  # 规范化地址
        self._is_inproc = self._address.startswith("inproc://")
        self._is_ipc = self._address.startswith("ipc://")

        if to_bind:
            self.to_bind = True
            self.init_publisher()
        if to_connect:
            self.to_connect = True
            self.init_subscriber()
            
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
        
    def init_publisher(self):
        """尝试绑定socket，处理已存在的情况"""
        if not self.to_bind:
            raise RuntimeError("Not in publisher mode")
        
        with MessageBus._bound_lock:
            # 检查是否已有绑定的socket
            if MessageBus._bound_socket:
                self._logger.warning(f"Address {self._address} already bound")
                return                
            try:
                # 对于IPC，先检查文件是否存在
                if self._is_ipc:
                    path = urlparse(self._address).path
                    if os.path.exists(path):
                        self._logger.warning(f"IPC file exists: {path}, treating as bound by another process")
                        MessageBus._bound_socket = True
                        return            
                # 创建socket并尝试绑定
                socket = self._context.socket(zmq.PUB)
                socket.bind(self._address)
                self._pub_socket = socket  # 只有绑定成功才保存socket
                MessageBus._bound_socket = self._pub_socket
                self._logger.info(f"Publisher bound to: {self._address}")
            except zmq.ZMQError as e:
                socket.close()  # 关闭失败的socket
                if e.errno == zmq.EADDRINUSE:
                    self._logger.warning(f"Address {self._address} in use by another process")
                    MessageBus._bound_socket = True  # 标记为外部绑定
                else:
                    raise
    @property
    def is_bound(self):
        return self._bound_socket is not None

    @property
    def is_connected(self):
        return self._sub_socket is not None

    @property
    def is_bound_outside(self):
        return MessageBus._bound_socket is True

    def init_subscriber(self):
        """初始化订阅者"""
        if not self.to_connect:
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
                time.sleep(0.1)
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

    async def collect_async(self, once: bool = True, timeout: float = None):
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

    def collect(self, once: bool = True, timeout: float = 30.0):
        """同步收集消息
        
        自动处理各种运行环境（Jupyter、测试、异步、同步等）
        
        Args:
            once: 是否只收集一次
            timeout: 超时时间（秒）
            
        Yields:
            dict: 收到的消息
        """
        def is_notebook():
            try:
                shell = get_ipython().__class__.__name__
                return shell in ('ZMQInteractiveShell', 'Shell')
            except NameError:
                return False
            
        def get_or_create_loop():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import nest_asyncio
                    nest_asyncio.apply()
                return loop
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop
            
        def cleanup_tasks(loop):
            """清理所有任务"""
            tasks = asyncio.all_tasks(loop)
            if not tasks:
                return
            
            for task in tasks:
                task.cancel()
            
            # 等待所有任务取消完成
            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            
            # 确保所有任务都已完成
            for task in tasks:
                if not task.done():
                    self._logger.warning(f"Task {task.get_name()} could not be cancelled")
            
        async def async_generator():
            try:
                async for msg in self.collect_async(once=once, timeout=timeout):
                    yield msg
            finally:
                if is_notebook():
                    loop = asyncio.get_running_loop()
                    current = asyncio.current_task(loop)
                    for task in asyncio.all_tasks(loop):
                        if task is not current and not task.done():
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
            
        def sync_wrapper():
            """同步包装器"""
            loop = get_or_create_loop()
            ait = async_generator()
            
            try:
                while True:
                    try:
                        yield loop.run_until_complete(ait.__anext__())
                    except StopAsyncIteration:
                        break
            finally:
                if is_notebook():
                    cleanup_tasks(loop)
                
        # 返回同步生成器
        yield from sync_wrapper()

    def check_event_loop_status(self):
        """检查事件循环状态（调试用）"""
        try:
            loop = asyncio.get_event_loop()
            pending = len(asyncio.all_tasks(loop))
            running = loop.is_running()
            return {
                'loop_running': running,
                'pending_tasks': pending
            }
        except Exception as e:
            return {'error': str(e)}
