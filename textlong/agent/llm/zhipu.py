from typing import Union, List, Optional, Dict, Any
from zhipuai import ZhipuAI

from ...io import TextBlock
from ..chat import ChatAgent

import os
import json

class ChatZhipu(ChatAgent):
    def __init__(self, model: str=None, tools=None, toolkits=None, **kwargs):
        super().__init__(threads_group="CHAT_ZHIPU", tools=tools, toolkits=toolkits, **kwargs)
        self.threads_group = "CHAT_ZHIPU"
        self.model = model or "glm-4-flash"
        self.api_key = kwargs.get("api_key", os.getenv("ZHIPUAI_API_KEY"))
        self.client = ZhipuAI(api_key=self.api_key, **kwargs)

    def generate(
        self,
        messages: List[dict],
        *args,
        **kwargs
    ):
        _kwargs = {
            "stream": True,
            "model": self.model,
            "tools": self.tools,
        }
        _kwargs.update({"messages": messages, **kwargs})

        completion = self.client.chat.completions.create(**_kwargs)

        for response in completion:
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
