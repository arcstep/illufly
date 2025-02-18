from typing import Union, List, Optional, Dict, Any
import asyncio
import logging

from ..models import TextChunk
from .chat_base import ChatBase

class ChatFake(ChatBase):
    """Fake Chat Service"""
    def __init__(
        self,
        response: Union[str, List[str]]=None, 
        sleep: float=0.1,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        # 处理响应设置
        if response is None:
            self.response = []
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

    async def generate(self, messages: Union[str, List[Dict[str, Any]]], **kwargs):
        """异步生成响应"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        self._logger.debug(f"Processing prompt: {str(messages)[:50]}...")
        
        # 获取响应内容
        resp_content = messages[-1]["content"]
        if not self.response:
            # 使用默认响应
            resp = f"Reply >> {resp_content}"
        else:
            resp = self.response[self.current_response_index]
            self.current_response_index = (self.current_response_index + 1) % len(self.response)
        
        # 逐字符发送响应
        for content in resp:
            await asyncio.sleep(self.sleep)
            yield TextChunk(text=content)
