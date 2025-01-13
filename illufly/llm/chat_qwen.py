import os
import json
from typing import List, Dict, Any
from http import HTTPStatus
from ..mq import StreamingService, StreamingBlock

class ChatQwen(StreamingService):
    """
    千问对话智能体
    """
    def __init__(self, model: str=None, enable_search: bool=False, api_key: str=None, base_url: str=None, extra_args: dict={}, **kwargs):
        try:
            import dashscope
            self.dashscope = dashscope
        except ImportError:
            raise ImportError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

        super().__init__(**kwargs)

        self.calling_args = {
            "model": model or "qwen-plus",
            "enable_search": enable_search
        }
        self.model_args = {
            "api_key": api_key or os.getenv("DASHSCOPE_API_KEY"),
            "base_url": base_url or os.getenv("DASHSCOPE_BASE_URL"),
            **extra_args
        }
        self.dashscope.api_key = self.model_args["api_key"]

    def _prepare_kwargs(self, messages: List[dict], **kwargs) -> dict:
        return {
            "messages": messages,
            "stream": True,
            "result_format": 'message',
            "incremental_output": True,
            **self.model_args,
            **self.calling_args,
            **kwargs
        }

    async def process(self, prompt: Dict[str, Any], **kwargs):
        messages = prompt
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
                        yield StreamingBlock(
                            block_type="tools_call_chunk",
                            content=json.dumps(func, ensure_ascii=False)
                        )
                else:
                    content = ai_output.content
                    yield StreamingBlock(
                        block_type="chunk",
                        content=content
                    )
            else:
                yield StreamingBlock(
                    block_type="error",
                    content=('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                        response.request_id, response.status_code,
                        response.code, response.message
                    ))
                )

        yield StreamingBlock(
            block_type="usage",
            content=json.dumps(usage, ensure_ascii=False)
        )