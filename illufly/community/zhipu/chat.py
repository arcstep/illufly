from typing import Union, List, Optional, Dict, Any

from ...io import EventBlock, NewLineBlock
from ...types import ChatAgent

import os
import json

class ChatZhipu(ChatAgent):
    def __init__(self, model: str=None, **kwargs):
        try:
            from zhipuai import ZhipuAI
        except ImportError:
            raise ImportError(
                "Could not import zhipuai package. "
                "Please install it via 'pip install -U zhipuai'"
            )

        super().__init__(threads_group="CHAT_ZHIPU", **kwargs)

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
        _kwargs.update({
            "messages": messages,
            **kwargs,
            **{"stream": True}
        })

        completion = self.client.chat.completions.create(**_kwargs)

        usage = {}
        output = []
        request_id = None
        for response in completion:
            if response.usage:
                request_id = response.id
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
