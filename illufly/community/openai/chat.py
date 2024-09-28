from typing import Union, List, Optional, Dict, Any

from ...io import TextBlock
from ...types import ChatAgent

import os
import json


class ChatOpenAI(ChatAgent):
    def __init__(self, model: str=None, tools=None, imitator: str=None, **kwargs):
        """
        使用 imitator 参数指定兼容 OpenAI 接口协议的模型来源，默认 imitator="OPENAI"。
        只需要在环境变量中配置 imitator 对应的 API_KEY 和 BASE_URL 即可。
        
        例如：
        QWEN_API_KEY=sk-...
        QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

        然后使用类似 `ChatOpenAI(imitator="QWEN")` 的代码就可以使用千问系列模型。
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "Could not import openai package. "
                "Please install it via 'pip install -U openai'"
            )

        imitator = (imitator or "").upper() or "OPENAI"
        super().__init__(threads_group=f"CHAT_{imitator}", tools=tools, **kwargs)

        self.default_call_args = {
            "model": model or os.getenv(f"{imitator}_MODEL_ID") or "gpt-3.5-turbo"
        }
        self.model_args = {
            "base_url": kwargs.pop("base_url", os.getenv(f"{imitator}_BASE_URL")),
            "api_key": kwargs.pop("api_key", os.getenv(f"{imitator}_API_KEY"))
        }
        self.client = OpenAI(**self.model_args)

    def generate(
        self,
        messages: List[dict],
        **kwargs
    ):
        from openai import OpenAI

        _kwargs = self.default_call_args
        tools_desc = self.get_tools_desc(kwargs.pop('tools', []))
        _kwargs.update({
            "messages": messages,
            "tools": tools_desc or None,
            **kwargs,
            **{"stream": True}
        })

        completion = self.client.chat.completions.create(**_kwargs)

        for response in completion:
            # print("response", response)
            if response.choices:
                ai_output = response.choices[0].delta
                if ai_output.tool_calls:
                    for func in ai_output.tool_calls:
                        func_json = {
                            "index": func.index or 0,
                            "id": func.id or "",
                            "type": func.type or "function",
                            "function": {
                                "name": func.function.name or "",
                                "arguments": func.function.arguments or ""
                            }
                        }
                        yield TextBlock("tools_call_chunk", json.dumps(func_json, ensure_ascii=False))
                else:
                    content = ai_output.content
                    if content:
                        yield TextBlock("chunk", content)
