import os
import json

from typing import Union, List, Optional
from openai import OpenAI

from ..io import TextBlock
from .base import ChatBase


class ChatOpenAI(ChatBase):
    def __init__(self, model: str=None, **kwargs):
        super().__init__(**kwargs)
        self.model = model or "gpt-3.5-turbo"
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate(
        self,
        prompt: Union[str, List[dict]],
        *args,
        **kwargs
    ):
        _prompt = prompt
        if isinstance(prompt, str):
            _prompt = [
                {
                    "role": "user",
                    "content": prompt
                }
            ]

        _kwargs = {
            "model": self.model,
            "stream": True,
            # "temperature": 0.8,
            # "top_p": 0.8,
            # # 可选，配置以后会在流式输出的最后一行展示token使用信息
            # "stream_options": {"include_usage": True}
        }
        _kwargs.update({"messages": _prompt, **kwargs})
        completion = self.client.chat.completions.create(**_kwargs)

        for response in completion:
            if response.choices:
                ai_output = response.choices[0].delta
                if ai_output.tool_calls:
                    for func in ai_output.tool_calls:
                        func_json = {
                            "index": func.index or 0,
                            "function": {
                                "id": func.id or "",
                                "type": func.type or "function",
                                "name": func.function.name,
                                "arguments": func.function.arguments
                            }
                        }
                        yield TextBlock("tools_call_chunk", json.dumps(func_json, ensure_ascii=False))
                else:
                    content = ai_output.content
                    if content:
                        yield TextBlock("chunk", content)
