from typing import Union, List, Optional, Dict, Any

import asyncio
import logging
import json

from ..models import TextChunk, ToolCallChunk, ToolCallFinal, TextFinal
from ..base_chat import BaseChat
from ..base_tool import BaseTool

class ChatFake(BaseChat):
    """Fake Chat Service"""
    def __init__(
        self,
        response: Union[str, List[str]]=None, 
        tool_responses: List[Dict] = None,  # 新增工具响应配置
        sleep: float=0.1
    ):
        super().__init__()
        
        # 处理响应设置
        if response is None:
            self.response = []
        elif isinstance(response, str):
            self.response = [response]
        else:
            self.response = response

        # 处理工具响应配置
        self.tool_responses = tool_responses or []
        self.tool_response_index = 0
        
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
        
        # 检查上一条消息是否是工具调用结果
        last_msg = messages[-1] if messages else None
        if last_msg and last_msg.get("role") == "tool":
            # 根据工具结果生成回复
            tool_result = last_msg.get("content", "")
            resp = f"Processed tool result: {tool_result}"
            for char in resp:
                await asyncio.sleep(self.sleep)
                yield TextChunk(text=char)
            
            yield TextFinal(text=resp)
            return
        
        # 检查是否需要返回工具调用
        if kwargs.get("tools") and self.tool_responses:
            tool_response = self.tool_responses[self.tool_response_index]
            self.tool_response_index = (self.tool_response_index + 1) % len(self.tool_responses)
            
            # 生成工具调用块
            tool_call_id = f"fake_tool_{self.tool_response_index}"
            yield ToolCallChunk(
                tool_call_id=tool_call_id,
                tool_name=tool_response["name"],
                arguments=json.dumps(tool_response["arguments"])
            )
            yield ToolCallFinal(
                tool_call_id=tool_call_id,
                tool_name=tool_response["name"],
                arguments=json.dumps(tool_response["arguments"])
            )
            return
        
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
        yield TextFinal(text=resp)
