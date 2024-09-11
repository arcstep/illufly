import os
import json

from typing import Union, List, Optional, Dict, Any
from openai import OpenAI

from ..io import TextBlock
from .agent import ChatAgent


class ChatOpenAI(ChatAgent):
    def __init__(self, model: str=None, **kwargs):
        super().__init__(threads_group="CHAT_OPENAI", **kwargs)
        self.threads_group = "CHAT_OPENAI"
        self.model = model or "gpt-3.5-turbo"
        self.client = OpenAI(api_key=kwargs.get("api_key", os.getenv("OPENAI_API_KEY")), **kwargs)

    def generate(
        self,
        messages: List[dict],
        *args,
        **kwargs
    ):
        _kwargs = {
            "model": self.model,
            "stream": True,
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
