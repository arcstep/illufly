from typing import AsyncGenerator, List

import asyncio
import time
from .utils import cleanup_connected_socket
from .models import BlockType, StreamingBlock
from .base import BaseMQ

class Subscriber(BaseMQ):
    """针对特定 thread_id 的 ZMQ 订阅者实例"""
    def __init__(self, thread_id: str=None, address: str=None, logger=None):
        super().__init__(address, logger)
        self._thread_id = thread_id or ""
        self._blocks = []  # 用于缓存收集到的消息
        self._is_collected = False  # 标记是否已完成收集
        self.to_connecting()

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

    async def _cleanup(self):
        """清理资源"""
        if self._connected_socket:
            cleanup_connected_socket(self._connected_socket, self._address, self._logger)
            self._connected_socket = None

    async def async_collect(self, timeout: float = None) -> AsyncGenerator[StreamingBlock, None]:
        """异步收集消息"""
        # 如果已经收集完成，直接返回缓存结果
        if self._is_collected:
            for block in self._blocks:
                yield block
            return

        # 首次收集
        try:
            start_time = time.time()
            while True:
                # 检查超时
                if timeout and time.time() - start_time > timeout:
                    break

                try:
                    if await self._connected_socket.poll(timeout=100):  # 100ms轮询
                        [topic_bytes, payload] = await self._connected_socket.recv_multipart()
                        message = json.loads(payload.decode())
                        block = StreamingBlock(**message)
                        
                        # 缓存消息
                        self._blocks.append(block)
                        yield block
                        
                        # 遇到结束标记，结束收集
                        if block.block_type == BlockType.END:
                            break
                            
                except zmq.error.ZMQError as e:
                    self._logger.error(f"ZMQ error during collection: {e}")
                    break

        finally:
            # 标记收集完成，清理资源
            self._is_collected = True
            await self._cleanup()

    def collect(self, timeout: float = None) -> Generator[StreamingBlock, None, None]:
        """同步收集消息"""
        return self._async_utils.wrap_async_generator(
            self.async_collect(timeout=timeout)
        )

    @property
    def is_collected(self) -> bool:
        """是否已完成收集"""
        return self._is_collected

    @property
    def blocks(self) -> List[StreamingBlock]:
        """获取缓存的消息"""
        return self._blocks.copy()
