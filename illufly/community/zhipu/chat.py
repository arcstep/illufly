from typing import Union, List, Optional, Dict, Any

from ...io import TextBlock
from ...types import ChatAgent

import os
import json

class ChatZhipu(ChatAgent):
    def __init__(self, model: str=None, tools=None, **kwargs):
        try:
            from zhipuai import ZhipuAI
        except ImportError:
            raise RuntimeError(
                "Could not import zhipuai package. "
                "Please install it via 'pip install -U zhipuai'"
            )

        super().__init__(threads_group="CHAT_ZHIPU", tools=tools, **kwargs)
        self.threads_group = "CHAT_ZHIPU"
        self.default_call_args = {
            "model": model or "glm-4-flash"
        }
        self.model_args = {
            "api_key": kwargs.get("api_key", os.getenv("ZHIPUAI_API_KEY")),
            "base_url": kwargs.get("base_url", os.getenv("ZHIPUAI_BASE_URL"))
        }
        self.client = ZhipuAI(**self.model_args)

    def generate(
        self,
        messages: List[dict],
        **kwargs
    ):
        from zhipuai import ZhipuAI

        _kwargs = self.default_call_args
        tools_desc = self.get_tools_desc(kwargs.pop('tools', []))
        _kwargs.update({
            "messages": messages,
            "tools": tools_desc,
            **kwargs,
            **{"stream": True}
        })

        completion = self.client.chat.completions.create(**_kwargs)

        usage = {}
        for response in completion:
            if response.usage:
                usage = response.usage
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
        if usage:
            usage_dict = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }
            yield TextBlock("usage", json.dumps(usage_dict, ensure_ascii=False))
