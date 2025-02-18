from typing import Union, List, Optional, Dict, Any

from ...mq import ServiceDealer, TextChunk, ToolCallChunk, StreamingBlock, UsageBlock

import os
import json

class ChatOpenAI(ServiceDealer):
    """OpenAI 对话模型"""

    def __init__(self, model: str=None, imitator: str=None, extra_args: dict={}, **kwargs):
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

        imitator = (imitator or "").upper() or "OPENAI"
        super().__init__(**kwargs)

        self.default_call_args = {
            "model": model or os.getenv(f"{imitator}_MODEL_ID") or "gpt-4o-mini"
        }
        self.model_args = {
            "base_url": kwargs.pop("base_url", os.getenv(f"{imitator}_BASE_URL")),
            "api_key": kwargs.pop("api_key", os.getenv(f"{imitator}_API_KEY")),
            **extra_args
        }
        self.client = AsyncOpenAI(**self.model_args)

    @ServiceDealer.service_method(name="chat", description="OpenAI Chat Service")
    async def _chat(
        self,
        messages: List[dict],
        **kwargs
    ):

        _kwargs = self.default_call_args
        _kwargs.update({
            "messages": messages,
            **kwargs,
            **{"stream": True, "stream_options": {"include_usage": True}}
        })

        completion = await self.client.chat.completions.create(**_kwargs)

        usage = None
        async for response in completion:
            if response.usage:
                usage = response.usage
            if response.choices:
                ai_output = response.choices[0].delta
                if ai_output.tool_calls:
                    for func in ai_output.tool_calls:
                        id = func.id or ""
                        name = func.function.name or ""
                        arguments = func.function.arguments or ""
                        yield ToolCallChunk(id=id, name=name, arguments=arguments)
                else:
                    content = ai_output.content
                    if content:
                        yield TextChunk(text=content)

            if usage:
                usage_dict = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens
                }
                yield UsageBlock(**usage_dict, model=_kwargs["model"], provider=imitator)
