import json
import os
import asyncio

from typing import Union, List, Optional, Dict, Any
from http import HTTPStatus

from ...io import EventBlock, NewLineBlock
from ...types import ChatAgent
from ..http import confirm_upload_file
from ...io import NewLineBlock
class ChatQwen(ChatAgent):
    def __init__(self, model: str=None, **kwargs):
        try:
            import dashscope
            self.dashscope = dashscope
        except ImportError:
            raise ImportError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

        super().__init__(threads_group="CHAT_QWEN", **kwargs)

        self.default_call_args = {
            "model": model or "qwen-plus",
            "enable_search": kwargs.pop("enable_search", False)
        }
        self.model_args = {
            "api_key": kwargs.get("api_key", os.getenv("DASHSCOPE_API_KEY")),
            "base_url": kwargs.get("base_url", os.getenv("DASHSCOPE_BASE_URL"))
        }

    def _prepare_kwargs(self, messages: List[dict], **kwargs) -> dict:
        self.dashscope.api_key = self.model_args["api_key"]

        _kwargs = {
            **self.model_args,
            **self.default_call_args
        }
        _kwargs.update({
            "messages": messages,
            **kwargs,
            **{
                "stream": True,
                "result_format": 'message',
                "incremental_output": True,
            }
        })
        return _kwargs

    def generate(self, messages: List[dict], **kwargs):
        _kwargs = self._prepare_kwargs(messages, **kwargs)

        # 调用生成接口
        responses = self.dashscope.Generation.call(**_kwargs)

        # 流输出
        request_id = None
        usage = {}
        output = []
        for response in responses:
            if response.status_code == HTTPStatus.OK:
                if 'usage' in response:
                    request_id = response.request_id
                    usage = response.usage
                ai_output = response.output.choices[0].message
                output.append(ai_output)
                if 'tool_calls' in ai_output:
                    for func in ai_output.tool_calls:
                        yield EventBlock("tools_call_chunk", json.dumps(func, ensure_ascii=False))
                else:
                    content = ai_output.content
                    yield EventBlock("chunk", content)
            else:
                yield EventBlock("warn", ('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                    response.request_id, response.status_code,
                    response.code, response.message
                )))

        yield NewLineBlock()
        yield EventBlock(
            "usage",
            json.dumps(usage, ensure_ascii=False),
            calling_info={
                "request_id": request_id,
                "input": _kwargs,
                "output": output,
            }
        )

    async def async_generate(self, messages: List[dict], **kwargs):
        _kwargs = self._prepare_kwargs(messages, **kwargs)

        # 调用生成接口
        responses = await self.dashscope.AioGeneration.call(**_kwargs)

        # 流输出
        usage = {}
        output = []
        request_id = None
        async for response in responses:
            if response.status_code == HTTPStatus.OK:
                if 'usage' in response:
                    request_id = response.request_id
                    usage = response.usage
                ai_output = response.output.choices[0].message
                output.append(ai_output)
                if 'tool_calls' in ai_output:
                    for func in ai_output.tool_calls:
                        yield EventBlock(
                            "tools_call_chunk",
                            json.dumps(func, ensure_ascii=False)
                        )
                else:
                    content = ai_output.content
                    yield EventBlock(
                        "chunk",
                        content
                    )
            else:
                yield EventBlock("warn", ('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                    response.request_id, response.status_code,
                    response.code, response.message
                )))

        yield NewLineBlock()
        yield EventBlock(
            "usage",
            json.dumps(usage, ensure_ascii=False),
            calling_info={
                "request_id": request_id,
                "input": _kwargs,
                "output": output,
            }
        )

class ChatQwenVL(ChatQwen):
    def __init__(self, model: str=None, **kwargs):
        super().__init__(model=(model or "qwen-vl-plus"), style="qwen_vl", **kwargs)

    def generate(self, messages: List[dict], **kwargs):
        for m in messages:
            if isinstance(m['content'], list):
                for obj in m['content']:
                    if isinstance(obj, dict) and "image" in obj:
                        obj["image"] = confirm_upload_file(self.default_call_args['model'], obj["image"], self.model_args['api_key'])
        _kwargs = self._prepare_kwargs(messages, **kwargs)
        _kwargs["headers"] = {"X-DashScope-OssResourceResolve": "enable"}

        # 调用生成接口
        responses = self.dashscope.MultiModalConversation.call(**_kwargs)

        # 流输出
        usage = {}
        output = []
        request_id = None
        for response in responses:
            if response.status_code == HTTPStatus.OK:
                if 'usage' in response:
                    request_id = response.request_id
                    usage = response.usage
                ai_output = response.output.choices[0].message
                if 'tool_calls' in ai_output:
                    for func in ai_output.tool_calls:
                        output.append({"tools_call_chunk": func})
                        yield EventBlock("tools_call_chunk", json.dumps(func, ensure_ascii=False))
                else:
                    content = ai_output.content
                    output.append({"chunk": content})
                    yield EventBlock("chunk", content)
            else:
                yield EventBlock("warn", ('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                    response.request_id, response.status_code,
                    response.code, response.message
                )))

        yield NewLineBlock()
        yield EventBlock(
            "usage",
            json.dumps(usage, ensure_ascii=False),
            calling_info={
                "request_id": request_id,
                "output": output,
                "input": _kwargs,
            }
        )

    async def async_generate(self, messages: List[dict], **kwargs):
        for block in await self.run_in_executor(self.generate, messages, **kwargs):
            yield block
