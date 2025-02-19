from typing import Union, List, Optional, Dict, Any

from ...mq.models import TextChunk, TextFinal, ToolCallChunk, ToolCallFinal, UsageBlock
from ..base_chat import BaseChat
from ..base_tool import BaseTool

import os
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
        final_tool_calls = {}  # 使用OrderedDict保持顺序
        last_tool_call_id = None
        async for response in completion:
            request_id = response.id
            model = response.model
            created_at = response.created

            if response.usage:
                usage = response.usage
            if response.choices:
                ai_output = response.choices[0].delta
                if ai_output.tool_calls:
                    for tool_call in ai_output.tool_calls:
                        # 处理ID可能分块到达的情况
                        tool_id = tool_call.id or last_tool_call_id
                        
                        if tool_id:
                            last_tool_call_id = tool_id
                        
                        # 初始化工具调用记录
                        if tool_id not in final_tool_calls:
                            final_tool_calls[tool_id] = {
                                'name': '',
                                'arguments': '',
                                'created_at': created_at,
                                'is_temp_id': not tool_call.id  # 标记临时ID
                            }
                        
                        # 累积各字段（处理字段分块到达）
                        current = final_tool_calls[tool_id]
                        current['name'] += tool_call.function.name or ""
                        current['arguments'] += tool_call.function.arguments or ""
                        
                        # 当收到正式ID时替换临时ID
                        if tool_call.id and current['is_temp_id']:
                            new_id = tool_call.id
                            final_tool_calls[new_id] = current
                            del final_tool_calls[tool_id]
                            current['is_temp_id'] = False
                        
                        # 实时生成chunk（即使字段不完整）
                        yield ToolCallChunk(
                            tool_call_id=tool_id,
                            tool_name=tool_call.function.name or "",
                            arguments=tool_call.function.arguments or "",
                            created_at=created_at
                        )
                else:
                    content = ai_output.content
                    if content:
                        final_text += content
                        yield TextChunk(request_id=request_id, model=model, text=content, created_at=created_at)
            
        # 生成最终结果（过滤空参数）
        for tool_id, data in final_tool_calls.items():
            if not data['arguments'].strip():
                continue
            
            # 清理临时ID标记
            data.pop('is_temp_id', None)
            
            yield ToolCallFinal(
                tool_call_id=tool_id,
                tool_name=data['name'].strip(),
                arguments=data['arguments'].strip(),
                created_at=data['created_at']
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
