from typing import Union, List, Optional
import os
import json

from ..io import TextBlock
from .base import ChatBase

from zhipuai import ZhipuAI

class ChatZhipu(ChatBase):
    def __init__(self, model: str=None, **kwargs):
        super().__init__(**kwargs)
        self.threads_group = "CHAT_ZHIPU"
        self.model = model or "glm-4-flash"
        self.api_key = kwargs.get("api_key", os.getenv("ZHIPUAI_API_KEY"))
        self.client = ZhipuAI(api_key=self.api_key, **kwargs)

    def generate(
        self,
        prompt: Union[str, List[dict]],
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
