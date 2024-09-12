from typing import Union, List, Optional, Dict, Any

from http import HTTPStatus
from ..io import TextBlock
from ..config import get_env
from .agent import ChatAgent

import dashscope
import json
import os

class ChatQwen(ChatAgent):
    def __init__(self, model: str=None, tools=None, toolkits=None, **kwargs):
        super().__init__(threads_group="CHAT_OPENAI", tools=tools, toolkits=toolkits, **kwargs)
        self.model = model or "qwen-max"
        self.api_key = kwargs.get("api_key", os.getenv("DASHSCOPE_API_KEY"))

    def generate(
        self,
        messages: List[dict],
        *args,
        **kwargs):

        _kwargs = {
            "model": self.model,
            "api_key": self.api_key,
            "tools": self.tools,
            "stream": True,
            "result_format": 'message',
            "incremental_output": True,
        }
        _kwargs.update({"messages": messages, **kwargs})

        # 调用生成接口
        responses = dashscope.Generation.call(**_kwargs)

        # 流输出
        for response in responses:
            if response.status_code == HTTPStatus.OK:
                ai_output = response.output.choices[0].message
                if 'tool_calls' in ai_output:
                    for func in ai_output.tool_calls:
                        yield TextBlock("tools_call_chunk", json.dumps(func, ensure_ascii=False))
                else:
                    content = ai_output.content
                    yield TextBlock("chunk", content)
            else:
                yield TextBlock("info", ('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                    response.request_id, response.status_code,
                    response.code, response.message
                )))
