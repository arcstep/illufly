from typing import Union, List, Optional, Dict, Any

from ...io import EventBlock, NewLineBlock
from ...types import ChatAgent
from ...utils import raise_invalid_params

import os
import json

class ChatOpenAI(ChatAgent):
    @classmethod
    def allowed_params(cls):
        return {
            "model": "模型名称",
            "imitator": "兼容 OpenAI 接口协议的模型来源，默认 imitator='OPENAI'，即从环境变量中读取 OPENAI_API_KEY 和 OPENAI_BASE_URL。",
            **ChatAgent.allowed_params()
        }

    def __init__(self, model: str=None, imitator: str=None, extra_args: dict={}, **kwargs):
        """
        使用 imitator 参数指定兼容 OpenAI 接口协议的模型来源，默认 imitator="OPENAI"。
        只需要在环境变量中配置 imitator 对应的 API_KEY 和 BASE_URL 即可。
        
        例如：
        QWEN_API_KEY=sk-...
        QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

        然后使用类似 `ChatOpenAI(imitator="QWEN")` 的代码就可以使用千问系列模型。
        """
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "Could not import openai package. "
                "Please install it via 'pip install -U openai'"
            )

        imitator = (imitator or "").upper() or "OPENAI"
        super().__init__(threads_group=f"CHAT_{imitator}", **kwargs)

        self.default_call_args = {
            "model": model or os.getenv(f"{imitator}_MODEL_ID") or "gpt-3.5-turbo"
        }
        self.model_args = {
            "base_url": kwargs.pop("base_url", os.getenv(f"{imitator}_BASE_URL")),
            "api_key": kwargs.pop("api_key", os.getenv(f"{imitator}_API_KEY")),
            **extra_args
        }
        self.client = OpenAI(**self.model_args)

    def generate(
        self,
        messages: List[dict],
        **kwargs
    ):
        from openai import OpenAI

        _kwargs = self.default_call_args
        _kwargs.update({
            "messages": messages,
            **kwargs,
            **{"stream": True, "stream_options": {"include_usage": True}}
        })

        completion = self.client.chat.completions.create(**_kwargs)

        usage = {}
        output = []
        request_id = None
        for response in completion:
            if response.usage:
                usage = response.usage
            if response.choices:
                ai_output = response.choices[0].delta
                if ai_output.tool_calls:
                    for func in ai_output.tool_calls:
                        func_json = {
                            # "index": func.index or 0,
                            "id": func.id or "",
                            "type": func.type or "function",
                            "function": {
                                "name": func.function.name or "",
                                "arguments": func.function.arguments or ""
                            }
                        }
                        output.append({"tools_call_chunk": func_json})
                        yield EventBlock("tools_call_chunk", json.dumps(func_json, ensure_ascii=False))
                else:
                    content = ai_output.content
                    if content:
                        output.append({"chunk": content})
                        yield EventBlock("chunk", content)
        yield NewLineBlock()
        usage_dict = {
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None
        }
        yield EventBlock(
            "usage",
            json.dumps(usage_dict, ensure_ascii=False),
            calling_info={
                "request_id": request_id,
                "input": _kwargs,
                "output": output,
            }
        )
