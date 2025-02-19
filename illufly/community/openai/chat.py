from typing import Union, List, Optional, Dict, Any

from ...mq.models import TextChunk, TextFinal, ToolCallChunk, ToolCallFinal, UsageBlock
from ..base_chat import BaseChat
from ..base_tool import BaseTool

import os
import json
import logging
import asyncio

class ChatOpenAI(BaseChat):
    """OpenAI 对话模型"""

    def __init__(self, model: str=None, imitator: str=None, logger: logging.Logger = None, **kwargs):
        """
        使用 imitator 参数指定兼容 OpenAI 接口协议的模型来源，默认 imitator="OPENAI"。
        只需要在环境变量中配置 imitator 对应的 API_KEY 和 BASE_URL 即可。
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "Could not import openai package. "
                "Please install it via 'pip install -U openai'"
            )

        self.imitator = (imitator or "").upper() or "OPENAI"
        super().__init__(logger=logger)

        self.default_call_args = {
            "model": model or os.getenv(f"{self.imitator}_MODEL_ID") or "gpt-4o-mini"
        }
        self.model_args = {
            "base_url": kwargs.pop("base_url", os.getenv(f"{self.imitator}_BASE_URL")),
            "api_key": kwargs.pop("api_key", os.getenv(f"{self.imitator}_API_KEY")),
            **kwargs
        }
        self.client = AsyncOpenAI(**self.model_args)

    async def generate(self, messages: Union[str, List[Dict[str, Any]]], tools: List[BaseTool] = None, **kwargs):

        _kwargs = self.default_call_args
        _kwargs.update({
            "messages": messages,
            "tools": [tool.to_openai_tool() for tool in (tools or [])],
            **kwargs,
            **{"stream": True, "stream_options": {"include_usage": True}}
        })

        completion = await self.client.chat.completions.create(**_kwargs)

        usage = None
        final_text = ""
        final_tool_calls_dict = {}
        async for response in completion:
            request_id = response.id
            model = response.model
            created_at = response.created

            if response.usage:
                usage = response.usage
            if response.choices:
                ai_output = response.choices[0].delta
                if ai_output.tool_calls:
                    for func in ai_output.tool_calls:
                        id = func.id or ""
                        name = func.function.name or ""
                        arguments = func.function.arguments or ""
                        if id not in final_tool_calls_dict:
                            final_tool_calls_dict[id] = {'name': name, 'arguments': arguments}
                        final_tool_calls_dict[id]['name'] += name
                        final_tool_calls_dict[id]['arguments'] += arguments
                        yield ToolCallChunk(
                            request_id=request_id,
                            model=model,
                            tool_call_id=id,
                            tool_name=name,
                            arguments=arguments,
                            created_at=created_at
                        )
                else:
                    content = ai_output.content
                    if content:
                        final_text += content
                        yield TextChunk(request_id=request_id, model=model, text=content, created_at=created_at)
            
        if final_tool_calls_dict:
            for id, tool_call in final_tool_calls_dict.items():
                yield ToolCallFinal(
                    request_id=request_id,
                    model=model,
                    tool_call_id=id,
                    tool_name=tool_call['name'],
                    arguments=tool_call['arguments'],
                    created_at=created_at
                )

        if final_text:
            yield TextFinal(request_id=request_id, model=model, text=final_text, created_at=created_at)

        if usage:
            usage_dict = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }
            yield UsageBlock(**usage_dict, model=model, request_id=request_id, provider=self.imitator, created_at=created_at)
