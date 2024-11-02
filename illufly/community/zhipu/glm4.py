from typing import Union, List, Optional, Dict, Any

from ...io import EventBlock, NewLineBlock
from ...types import ChatAgent
from ...utils import raise_invalid_params
from ..http import (
    EventBlock,

    get_headers,
    validate_output_path,

    send_request,
    check_task_status,
    save_resource,

    async_send_request,
    async_check_task_status,
    async_save_resource,

    confirm_base64_or_uri
)

import os
import json

class ChatZhipu(ChatAgent):
    @classmethod
    def allowed_params(cls):
        return {
            "model": "模型名称",
            **ChatAgent.allowed_params()
        }

    def __init__(self, model: str=None, extra_args: dict={}, **kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())
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
            "base_url": kwargs.get("base_url", os.getenv("ZHIPUAI_BASE_URL")),
            **extra_args
        }
        self.client = ZhipuAI(**self.model_args)

    def generate(
        self,
        messages: List[dict],
        **kwargs
    ):
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

class ChatZhipuVL(ChatZhipu):
    def __init__(self, model: str=None, **kwargs):
        super().__init__(model=(model or "glm-4v-plus"), style="openai_vl", **kwargs)

    def generate(self, messages: List[dict], **kwargs):
        for m in messages:
            if isinstance(m['content'], list):
                for obj in m['content']:
                    if isinstance(obj, dict):
                        if obj['type'] == "image_url":
                            obj['image_url']['url'] = confirm_base64_or_uri(obj['image_url']['url'])
                        elif obj['type'] == "video_url":
                            obj['video_url']['url'] = confirm_base64_or_uri(obj['video_url']['url'])
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
