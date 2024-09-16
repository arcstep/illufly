from typing import Union, List, Optional, Dict, Any
from openai import OpenAI
from langchain_core.tools import BaseTool

from ...io import TextBlock
from ..chat import ChatAgent

import os
import json


class ChatOpenAI(ChatAgent):
    def __init__(self, model: str=None, tools=None, **kwargs):
        super().__init__(threads_group="CHAT_OPENAI", tools=tools, **kwargs)
        self.threads_group = "CHAT_OPENAI"
        self.default_call_args = {"model": model or "gpt-3.5-turbo"}
        self.model_args = {"api_key": kwargs.pop("api_key", os.getenv("OPENAI_API_KEY"))}

    def generate(
        self,
        messages: List[dict],
        *args,
        **kwargs
    ):
        _kwargs = {"stream": True, **self.default_call_args}
        tools_desc = self.get_tools_desc(kwargs.pop('tools', []))
        _kwargs.update({
            "messages": messages,
            "tools": tools_desc,
            **kwargs
        })

        client = OpenAI(**self.model_args)
        completion = client.chat.completions.create(**_kwargs)

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
