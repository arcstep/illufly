from typing import AsyncGenerator, List, Generator, Union

import zmq
import asyncio
import time
import json

from ..utils import cleanup_connected_socket, normalize_address
from ..models import BlockType, StreamingBlock, EndBlock, TextChunk, ErrorBlock
from ..base_mq import BaseMQ

class Subscriber(BaseMQ):
    """针对特定 thread_id 的 ZMQ 订阅者实例"""
    def __init__(self, thread_id: str=None, address: str=None, logger=None, poll_interval: int=500, timeout: float=None):
        """初始化订阅者
        
        Args:
            thread_id: 线程ID
            address: ZMQ地址
            logger: 日志记录器
            poll_interval: 轮询间隔(毫秒)，默认500ms
            timeout: 消息之间的最大间隔时间(秒)
        """
        address = normalize_address(address or "inproc://message_bus")
        super().__init__(address, logger)
        self._thread_id = thread_id or ""
        self._blocks = []  # 缓存的消息
        self._is_collected = False  # 是否完成收集
        self._connected_socket = None
        self._poll_interval = poll_interval  # 新增轮询间隔参数
        self._timeout = timeout
        self.to_connecting()
        self._logger.info(f"Subscriber initialized with thread_id: {self._thread_id}")

        # 订阅任务结束之后，执行清理
        self.on_exit = lambda: None

    def to_connecting(self):
        """初始化订阅者"""
        if not self._is_collected:  # 只有未收集完成时才需要连接
            try:
                self._connected_socket = self._context.socket(zmq.SUB)
                self._connected_socket.connect(self._address)
                self._connected_socket.subscribe(self._thread_id.encode())
                self._logger.info(f"Subscriber connected to: {self._address}")
            except Exception as e:
                self._logger.error(f"Connection error: {e}")
                raise

    def cleanup(self):
        """清理资源"""
        self._logger.info(f"Cleaning up subscriber for thread: {self._thread_id}")
        if self._connected_socket:
            cleanup_connected_socket(self._connected_socket, self._address, self._logger)
            self._connected_socket = None

    def __del__(self):
        """析构函数，确保资源被清理"""
        self._logger.info(f"Subscriber being destroyed for thread: {self._thread_id}")
        self.cleanup()

    async def async_collect(self, block_types: Union[List[BlockType], BlockType]=None) -> AsyncGenerator[StreamingBlock, None]:
        """异步收集消息"""
        if isinstance(block_types, (BlockType, str)):
            block_types = [block_types]

        self._logger.info(f"Starting async_collect with is_collected={self._is_collected}, cached blocks={len(self._blocks)}")
        if self._is_collected:
            self._logger.info(f"Using cached blocks, block_types={block_types}")
            filtered_blocks = [block for block in self._blocks if block_types is None or block.block_type in block_types]
            for block in filtered_blocks:
                yield block
            return

        try:
            last_message_time = time.time()
            self._logger.info(f"Starting new collection for thread: {self._thread_id}")
            
            while True:
                try:
                    if await self._connected_socket.poll(timeout=self._poll_interval):
                        [topic_bytes, payload] = await self._connected_socket.recv_multipart()
                        data = json.loads(payload.decode())
                        block = StreamingBlock.create_block(**data)
                        
                        self._logger.debug(f"Received block: {block}")
                        
                        current_time = time.time()
                        if self._timeout and (current_time - last_message_time > self._timeout):
                            self._logger.warning(f"Message interval exceeded timeout of {self._timeout}s")
                            error_block = ErrorBlock(error="Message timeout")
                            self._blocks.append(error_block)
                            yield error_block
                            self._is_collected = True
                            break
                        
                        last_message_time = current_time
                        self._blocks.append(block)
                        if block_types is None or block.block_type in block_types:
                            yield block
                        
                        if block.block_type == BlockType.END:
                            self._logger.info(f"Received END block for thread: {self._thread_id}")
                            self._is_collected = True
                            break
                            
                    elif self._timeout and (time.time() - last_message_time > self._timeout):
                        self._logger.warning(f"No message received for {self._timeout}s")
                        error_block = StreamingBlock.create_error("Message timeout")
                        self._blocks.append(error_block)
                        yield error_block
                        self._is_collected = True
                        break
                        
                except zmq.error.ZMQError as e:
                    self._logger.error(f"ZMQ error for thread {self._thread_id}: {e}")
                    error_block = StreamingBlock.create_error(str(e))
                    self._blocks.append(error_block)
                    yield error_block
                    self._is_collected = True
                    break
        
        except Exception as e:
            self._logger.error(f"Collection error for thread {self._thread_id}: {e}")
            raise
        finally:
            self.on_exit()
            self._logger.info(f"Collection finished for thread {self._thread_id}, collected blocks: {len(self._blocks)}")

    def collect(self, block_types: Union[List[BlockType], BlockType]=None) -> Generator[StreamingBlock, None, None]:
        """同步收集消息"""
        if isinstance(block_types, (BlockType, str)):
            block_types = [block_types]

        self._logger.info(f"Starting sync collect for thread: {self._thread_id}")
        return self._async_utils.wrap_async_generator(
            self.async_collect(block_types)
        )

    @property
    def is_collected(self) -> bool:
        """是否已完成收集"""
        return self._is_collected

    @property
    def blocks(self) -> List[StreamingBlock]:
        """获取缓存的消息"""
        return self._blocks.copy()
