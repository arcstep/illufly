from typing import Union, List, Optional, Dict, Any

from ..base_chat import BaseChat
from ..base_tool import BaseTool
from ..models import TextChunk, TextFinal, ToolCallChunk, ToolCallFinal, UsageBlock

import os
import logging
import asyncio

class ChatOpenAI(BaseChat):
    """OpenAI 对话模型"""

    def __init__(self, model: str=None, imitator: str=None, **kwargs):
        """
        使用 imitator 参数指定兼容 OpenAI 接口协议的模型来源，默认 imitator="OPENAI"。
        只需要在环境变量中配置 imitator 对应的 API_KEY 和 BASE_URL 即可。
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "Could not import openai package. "
                "Please install it via 'pip install -U openai'"
            )

        self.imitator = (imitator or "").upper() or "OPENAI"
        super().__init__()

        # 按照 imitator 参数指定组名，以便于作为 DEALER 服务注册时按 imitator 作为默认分组
        self.group = self.imitator

        self.default_call_args = {
            "model": model or os.getenv(f"{self.imitator}_MODEL_ID") or "gpt-4o-mini"
        }
        self.model_args = {
            "base_url": kwargs.pop("base_url", os.getenv(f"{self.imitator}_BASE_URL")),
            "api_key": kwargs.pop("api_key", os.getenv(f"{self.imitator}_API_KEY")),
            **kwargs
        }
        self.client = AsyncOpenAI(**self.model_args)

    async def list_models(self) -> List[Dict[str, Any]]:
        """列出所有模型，返回包含关键信息的字典列表"""
        try:
            response = await self.client.models.list()
            if response.data:
                return [{
                    "id": model.id,
                    "owned_by": model.owned_by,
                    "object": model.object,
                } for model in response.data]
            else:
                return []
        except Exception as e:
            self._logger.error(f"列出模型失败: {e}")
            return []

    async def generate(self, messages: Union[str, List[Dict[str, Any]]], **kwargs):

        _kwargs = self.default_call_args
        _kwargs.update({
            "messages": messages,
            **kwargs,
            **{"stream": True, "stream_options": {"include_usage": True}}
        })

        completion = await self.client.chat.completions.create(**_kwargs)

        usage = None
        finish_reason = None
        model = None
        final_text = ""
        final_tool_calls = {}
        last_tool_call_id = None
        response_id = ""
        count = 0
        try:
            async for response in completion:
                # 打印流式块信息
                self._logger.debug(
                    f"收到流式块 | ID: {response.id} "
                    f"response: {response}"
                )
                
                count += 1
                # 新增结束条件检查
                if count > 1000:
                    self._logger.debug(f"超出循环次数，结束循环 >>> count: {count}")
                    break
                elif not response.choices:
                    self._logger.debug("流数据结束传输")
                    break

                model = response.model
                created_at = response.created
                response_id = response.id
                finish_reason = response.choices[0].finish_reason

                if response.usage:
                    usage = response.usage

                ai_output = response.choices[0].delta if response.choices else None
                if ai_output.tool_calls:
                    for tool_call in ai_output.tool_calls:
                        # 处理ID可能分块到达的情况
                        tool_id = tool_call.id or last_tool_call_id
                        
                        if tool_id:
                            last_tool_call_id = tool_id
                        
                        # 初始化工具调用记录
                        if tool_id not in final_tool_calls.keys():
                            final_tool_calls[tool_id] = {
                                'name': '',
                                'arguments': '',
                                'created_at': created_at,
                            }
                        
                        # 累积各字段（处理字段分块到达）
                        current = final_tool_calls[tool_id]
                        current['name'] += tool_call.function.name or ""
                        current['arguments'] += tool_call.function.arguments or ""
                        self._logger.debug(f"current tool_calls >>> {final_tool_calls}")

                        # 实时生成chunk（即使字段不完整）
                        yield ToolCallChunk(
                            service_name=f"{self.imitator}({model})",
                            response_id=response.id,
                            tool_call_id=tool_id,
                            tool_name=tool_call.function.name or "",
                            arguments=tool_call.function.arguments or "",
                            created_at=created_at,
                            model=model,
                            finish_reason=finish_reason
                        )

                else:
                    content = ai_output.content
                    if content:
                        final_text += content
                        self._logger.debug(f"收到流式文本块: {content}")
                        yield TextChunk(
                            service_name=f"{self.imitator}({model})",
                            response_id=response.id,
                            text=content,
                            model=model,
                            finish_reason=finish_reason,
                            created_at=created_at
                        )

                # 如果返回携带了结束信号，则退出循环
                if finish_reason:
                    yield TextChunk(
                        service_name=f"{self.imitator}({model})",
                        response_id=response.id,
                        text="",
                        model=model,
                        finish_reason=finish_reason,
                        created_at=created_at
                    )
                    self._logger.debug(f"收到流式结束信号: {finish_reason}")
                    break

            # 循环结束后立即释放资源
            await completion.close()  # 确保资源释放
            self._logger.debug("流式连接已关闭")
            
            # 生成最终结果
            if final_tool_calls:
                self._logger.debug(f"final_tool_calls >>> {final_tool_calls}")
                for key, call_data in final_tool_calls.items():
                    yield ToolCallFinal(
                        service_name=f"{self.imitator}({model})",
                        response_id=response_id,
                        model=model,
                        finish_reason=finish_reason,
                        tool_call_id=key,
                        tool_name=call_data['name'].strip(),
                        arguments=call_data['arguments'].strip(),
                        created_at=call_data['created_at']
                    )

            if final_text:
                yield TextFinal(
                    service_name=f"{self.imitator}({model})",
                    response_id=response_id,
                    text=final_text,
                    created_at=created_at
                )

            if usage:
                usage_dict = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens
                }
                yield UsageBlock(
                    **usage_dict,
                    response_id=response_id,
                    service_name=f"{self.imitator}({model})",
                    model=model,
                    provider=self.imitator,
                    created_at=created_at
                )

        except asyncio.CancelledError:
            self._logger.warning("流式请求被取消")
