from typing import Union, List, Optional

from http import HTTPStatus
from ..io import TextBlock
from ..config import get_env
from .base import ChatBase

import dashscope
import json
import os

class ChatQwen(ChatBase):
    def __init__(self, model: str=None, **kwargs):
        super().__init__(**kwargs)
        self.threads_group = "CHAT_QWEN"
        self.model = model or "qwen-max"
        self.api_key = kwargs.get("api_key", os.getenv("DASHSCOPE_API_KEY"))

    def generate(
        self,
        prompt: Union[str, List[dict]],
        **kwargs):

        # 转换消息格式
        _messages = None
        _prompt = None
        if isinstance(prompt, str):
            _prompt = prompt
        else:
            _messages = prompt

        _kwargs = {
            "model": self.model,
            "api_key": self.api_key,
            "stream": True,
            "result_format": 'message',
            "incremental_output": True,
            # "seed": 1234,
            # "top_p": 0.8,
            # "max_tokens": 1500,
            # "temperature": 0.85,
            # "repetition_penalty": 1.0,
        }
        _kwargs.update({"messages": _messages, "prompt":_prompt, **kwargs})

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
