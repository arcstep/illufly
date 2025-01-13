from typing import Union, List, AsyncGenerator, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import threading
import zmq.asyncio
import uuid
import json
from enum import Enum
import logging

from ..mq import StreamingService, StreamingBlock

class ChatFake(StreamingService):
    """Fake Chat Service"""
    def __init__(
        self, 
        response: Union[str, List[str]]=None, 
        sleep: float=0.1,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._logger = kwargs.get("logger", logging.getLogger(__name__))
        
        # 处理响应设置
        if response is None:
            self.response = []  # 空列表表示使用默认响应
        elif isinstance(response, str):
            self.response = [response]
        else:
            self.response = response
            
        self.sleep = sleep
        self.current_response_index = 0
        
        self._logger.info(
            f"Initializing FakeChat with "
            f"response_length: {len(self.response)}, "
            f"sleep: {self.sleep}s"
        )

    async def process(self, prompt: str, **kwargs):
        """异步生成响应"""
        self._logger.debug(f"Processing prompt: {prompt[:50]}...")
        
        # 发送初始信息
        yield StreamingBlock(block_type="info", content="I am FakeLLM")
        
        # 获取响应内容
        if not self.response:
            # 使用默认响应
            resp = f"Reply >> {prompt}"
        else:
            resp = self.response[self.current_response_index]
            self.current_response_index = (self.current_response_index + 1) % len(self.response)
        
        # 逐字符发送响应
        for content in resp:
            await asyncio.sleep(self.sleep)
            yield StreamingBlock(block_type="chunk", content=content)
        
