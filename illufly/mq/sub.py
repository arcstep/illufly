from typing import AsyncGenerator, List, Generator

import asyncio
import time
from .utils import cleanup_connected_socket, normalize_address
from .models import BlockType, StreamingBlock
from .base import BaseMQ

class Subscriber(BaseMQ):
    """针对特定 thread_id 的 ZMQ 订阅者实例"""
    def __init__(self, thread_id: str=None, address: str=None, logger=None):
        address = normalize_address(address or "inproc://message_bus")
        super().__init__(address, logger)
        self._thread_id = thread_id or ""
        self._blocks = []  # 缓存的消息
        self._is_collected = False  # 是否完成收集
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

    def cleanup(self):
        """清理资源"""
        if self._connected_socket:
            cleanup_connected_socket(self._connected_socket, self._address, self._logger)
            self._connected_socket = None

    def __del__(self):
        """析构函数，确保资源被清理"""
        self.cleanup()

    async def async_collect(self, timeout: float = None) -> AsyncGenerator[StreamingBlock, None]:
        """异步收集消息
        
        Args:
            timeout: float, 消息之间的最大间隔时间，而不是总收集时间
        """
        # 如果已经收集完成，直接返回缓存
        if self._is_collected:
            for block in self._blocks:
                yield block
            return

        if not self._connected_socket:
            self.to_connecting()  # 确保连接就绪

        try:
            while True:
                try:
                    # 使用较短的轮询间隔，但确保不超过用户设置的超时
                    poll_timeout = min(100, timeout * 1000) if timeout else 100
                    
                    if await self._connected_socket.poll(timeout=poll_timeout):
                        [topic_bytes, payload] = await self._connected_socket.recv_multipart()
                        message = json.loads(payload.decode())
                        block = StreamingBlock(**message)
                        
                        # 缓存并yield消息
                        self._blocks.append(block)
                        yield block
                        
                        # 遇到结束标记，结束收集
                        if block.block_type == BlockType.END:
                            self._is_collected = True
                            self.cleanup()
                            break
                    else:
                        # 如果设置了超时且没有收到消息，认为是超时
                        if timeout:
                            self._logger.warning(f"Message timeout after {timeout}s")
                            self._blocks.append(StreamingBlock.create_error("Message timeout"))
                            yield self._blocks[-1]
                            self._is_collected = True
                            self.cleanup()
                            break
                            
                except zmq.error.ZMQError as e:
                    self._logger.error(f"ZMQ error during collection: {e}")
                    self._blocks.append(StreamingBlock.create_error(str(e)))
                    yield self._blocks[-1]
                    self._is_collected = True
                    self.cleanup()
                    break

        except asyncio.CancelledError:
            self._logger.debug("Collection cancelled")
            self.cleanup()
            raise
        except Exception as e:
            self._logger.error(f"Unexpected error during collection: {e}")
            self._blocks.append(StreamingBlock.create_error(str(e)))
            yield self._blocks[-1]
            self._is_collected = True
            self.cleanup()

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
