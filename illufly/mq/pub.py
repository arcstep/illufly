import json
import zmq

from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator
from enum import Enum, auto

from .models import StreamingBlock, BlockType
from .utils import cleanup_bound_socket, normalize_address
from .base import BaseMQ

class Publisher(BaseMQ):
    """ZMQ 发布者，可直接使用默认实例"""
    def __init__(self, address=None, logger=None):
        address = normalize_address(address or "inproc://message_bus")
        super().__init__(address, logger)
        self.to_binding()

    def to_binding(self):
        """初始化发布者socket"""
        try:
            self._bound_socket = self._context.socket(zmq.PUB)
            self._bound_socket.bind(self._address)
            self._logger.debug(f"Publisher socket bound to {self._address}")
        except zmq.ZMQError as e:
            self._logger.error(f"Failed to bind publisher socket: {e}")
            raise

    def publish(self, topic: str, message: Union[dict, str, StreamingBlock]):
        """发布消息，如果存在订阅套接字则自动订阅"""
        if not isinstance(topic, str):
            raise ValueError("Topic must be a string")
        if not self._bound_socket:
            raise RuntimeError("No bound socket found")

        if message:
            if isinstance(message, str):
                message = StreamingBlock.create_chunk(content=message)
            elif isinstance(message, dict):
                message = StreamingBlock(**message)
            
            if not isinstance(message, StreamingBlock):
                raise ValueError("Message must be a StreamingBlock, a string or a dict")
        else:
            raise ValueError("Message is required")

        try:
            # 使用multipart发送消息
            self._bound_socket.send_multipart([
                topic.encode(),
                json.dumps(message.model_dump()).encode()
            ])
            self._logger.debug(f"Published to {topic}: {message}")

        except Exception as e:
            self._logger.error(f"Publish failed: {e}")
            raise

    def end(self, topic: str):
        """发送结束标记"""
        self.publish(topic, StreamingBlock.create_end())

    def cleanup(self):
        """清理资源"""
        cleanup_bound_socket(self._bound_socket, self._address, self._logger)

    def __del__(self):
        """析构函数，确保资源被清理"""
        self.cleanup()

# 创建默认实例
DEFAULT_PUBLISHER = Publisher()
