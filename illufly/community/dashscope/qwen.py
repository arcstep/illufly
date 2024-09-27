import json
import os

from typing import Union, List, Optional, Dict, Any
from http import HTTPStatus

from ...io import TextBlock
from ...types import ChatAgent
from ..http import confirm_upload_file

class ChatQwen(ChatAgent):
    def __init__(self, model: str=None, tools=None, **kwargs):
        try:
            import dashscope
        except ImportError:
            raise RuntimeError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

        enable_search = kwargs.pop("enable_search", False)
        super().__init__(threads_group="CHAT_QWEN", style="qwen", tools=tools, **kwargs)
        self.default_call_args = {
            "model": model or "qwen-plus"
        }
        self.model_args = {
            "api_key": kwargs.get("api_key", os.getenv("DASHSCOPE_API_KEY")),
            "base_url": kwargs.get("base_url", os.getenv("DASHSCOPE_BASE_URL")),
            "enable_search": enable_search
        }

    def generate(
        self,
        messages: List[dict],
        **kwargs
    ):
        import dashscope
        dashscope.api_key = self.model_args["api_key"]

        _kwargs = {
            "stream": True,
            "result_format": 'message',
            "incremental_output": True,
            **self.model_args,
            **self.default_call_args,
        }
        tools_desc = self.get_tools_desc(kwargs.pop('tools', []))
        _kwargs.update({
            "messages": messages,
            "tools": tools_desc,
            **kwargs
        })
        print("_kwargs", _kwargs)

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

class ChatQwenVL(ChatAgent):
    def __init__(self, model: str=None, tools=None, **kwargs):
        try:
            import dashscope
        except ImportError:
            raise RuntimeError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

        enable_search = kwargs.pop("enable_search", False)
        super().__init__(threads_group="CHAT_QWEN", style="qwen", tools=tools, **kwargs)
        self.default_call_args = {
            "model": model or "qwen-vl-plus",
            "enable_search": enable_search
        }
        self.model_args = {
            "api_key": kwargs.get("api_key", os.getenv("DASHSCOPE_API_KEY")),
            "base_url": kwargs.get("base_url", os.getenv("DASHSCOPE_BASE_URL")),
        }

    def generate(
        self,
        messages: List[dict],
        **kwargs
    ):
        import dashscope
        dashscope.api_key = self.model_args["api_key"]

        _kwargs = {
            "stream": True,
            "result_format": 'message',
            "incremental_output": True,
            **self.model_args,
            **self.default_call_args,
        }
        tools_desc = self.get_tools_desc(kwargs.pop('tools', []))
        has_upload = False
        for m in messages:
            if isinstance(m['content'], list):
                for obj in m['content']:
                    if isinstance(obj, dict) and "image" in obj:
                        obj["image"] = confirm_upload_file(self.default_call_args['model'], obj["image"], self.model_args['api_key'])
                        has_upload = True
        _kwargs.update({
            "messages": messages,
            "tools": tools_desc,
            "headers": {"X-DashScope-OssResourceResolve": "enable"} if has_upload else {},
            **kwargs
        })

        # 调用生成接口
        responses = dashscope.MultiModalConversation.call(**_kwargs)

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
