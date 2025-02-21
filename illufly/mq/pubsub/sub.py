from typing import AsyncGenerator, List, Generator, Union

import zmq
import asyncio
import time
import json

from ..utils import cleanup_connected_socket, normalize_address
from ..models import BlockType, StreamingBlock, EndBlock, ErrorBlock
from .base_mq import BaseMQ

class Subscriber(BaseMQ):
    """针对特定 request_id 的 ZMQ 订阅者实例"""
    def __init__(self, request_id: str=None, address: str=None, logger=None, timeout: int=30*1000):
        """初始化订阅者
        
        Args:
            request_id: 使用请求ID作为订阅主题
            address: ZMQ地址
            logger: 日志记录器
            timeout: 消息之间的最大间隔时间(秒)，如果设置为 -1 就是永远等待
        """
        address = normalize_address(address or "inproc://message_bus")
        super().__init__(address, logger)
        self._request_id = request_id or ""
        self._blocks = []  # 缓存的消息
        self._is_collected = False  # 是否完成收集
        self._connected_socket = None
        self._timeout = timeout
        self.to_connecting()
        self._logger.info(f"Subscriber initialized with request_id: {self._request_id}")

        # 订阅任务结束之后，执行清理
        self.on_exit = lambda: None

    def to_connecting(self):
        """初始化订阅者"""
        if not self._is_collected:  # 只有未收集完成时才需要连接
            try:
                self._connected_socket = self._context.socket(zmq.SUB)
                self._connected_socket.setsockopt(zmq.RCVTIMEO, self._timeout)
                self._connected_socket.connect(self._address)
                self._connected_socket.subscribe(self._request_id.encode())
                self._logger.info(f"Subscriber connected to: {self._address}")
            except Exception as e:
                self._logger.error(f"Connection error: {e}")
                raise

    def cleanup(self):
        """清理资源"""
        self._logger.info(f"Cleaning up subscriber for thread: {self._request_id}")
        if self._connected_socket:
            cleanup_connected_socket(self._connected_socket, self._address, self._logger)
            self._connected_socket = None

    def __del__(self):
        """析构函数，确保资源被清理"""
        self._logger.info(f"Subscriber being destroyed for thread: {self._request_id}")
        self.cleanup()

    async def async_collect(self, block_types: Union[List[BlockType], BlockType]=None) -> AsyncGenerator[StreamingBlock, None]:
        """异步收集消息"""
        if isinstance(block_types, (BlockType, str)):
            block_types = [block_types]

        if self._is_collected:
            filtered_blocks = [block for block in self._blocks if block_types is None or block.block_type in block_types]
            for block in filtered_blocks:
                yield block
            return

        try:
            last_message_time = time.time()
            self._logger.info(f"Starting new collection for thread: {self._request_id}")
            
            while True:
                try:
                    try:
                        [_, payload] = await self._connected_socket.recv_multipart()
                        data = json.loads(payload.decode())
                        block = StreamingBlock.create_block(**data)
                        
                        self._logger.debug(f"Received block: {block}")                            
                        self._blocks.append(block)
                        if block_types is None or block.block_type in block_types:
                            yield block
                        
                        if block.block_type == BlockType.END:
                            self._logger.info(f"Received END block for thread: {self._request_id}")
                            self._is_collected = True
                            break

                    except zmq.error.ZMQError as e:
                        if e.errno == zmq.EAGAIN:
                            # ZMQ 接收超时
                            timeout_info = f"ZMQ receive timeout after {self._timeout} ms"
                            self._logger.warning(timeout_info)
                            error_block = ErrorBlock(request_id=self._request_id, error=timeout_info)
                            self._blocks.append(error_block)
                            yield error_block
                            self._is_collected = True
                            break
                        else:
                            raise

                except Exception as e:
                    self._logger.error(f"Subscribing error for thread {self._request_id}: {e}")
                    error_block = ErrorBlock(request_id=self._request_id, error=str(e))
                    self._blocks.append(error_block)
                    yield error_block
                    self._is_collected = True
                    break
        
        except Exception as e:
            self._logger.error(f"Collection error for thread {self._request_id}: {e}")
            raise
        finally:
            self.on_exit()
            self._logger.info(f"Collection finished for thread {self._request_id}, collected blocks: {len(self._blocks)}")

    def collect(self, block_types: Union[List[BlockType], BlockType]=None) -> Generator[StreamingBlock, None, None]:
        """同步收集消息"""
        if isinstance(block_types, (BlockType, str)):
            block_types = [block_types]

        self._logger.info(f"Starting sync collect for thread: {self._request_id}")
        return self._async_utils.wrap_async_generator(
            self.async_collect(block_types)
        )
    
    def log(self, block_types: Union[List[BlockType], BlockType]=["text_chunk"], end: str="\n"):
        """打印日志"""
        blocks = self.collect(block_types)
        for b in blocks:
            print(b.content, end=end)

    @property
    def is_collected(self) -> bool:
        """是否已完成收集"""
        return self._is_collected

    @property
    def blocks(self) -> List[StreamingBlock]:
        """获取缓存的消息"""
        return self._blocks.copy()
