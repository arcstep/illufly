from typing import Union, List, Optional, Dict, Any

from ..base_chat import BaseChat
from ..base_tool import BaseTool
from ..models import TextChunk, TextFinal, ToolCallChunk, ToolCallFinal, UsageBlock

import os
import logging
import asyncio

class ChatOpenAI(BaseChat):
    """OpenAI 对话模型"""

    def __init__(self, model: str=None, imitator: str=None, logger: logging.Logger = None, **kwargs):
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
        super().__init__(logger=logger)

        # 按照 imitator 参数指定组名，以便于作为 DEALER 服务注册时按 imitator 作为默认分组
        self.group = self.imitator.lower()

        self.default_call_args = {
            "model": model or os.getenv(f"{self.imitator}_MODEL_ID") or "gpt-4o-mini"
        }
        self.model_args = {
            "base_url": kwargs.pop("base_url", os.getenv(f"{self.imitator}_BASE_URL")),
            "api_key": kwargs.pop("api_key", os.getenv(f"{self.imitator}_API_KEY")),
            **kwargs
        }
        self.client = AsyncOpenAI(**self.model_args)

    async def generate(self, messages: Union[str, List[Dict[str, Any]]], tools: List[BaseTool] = None, **kwargs):

        _kwargs = self.default_call_args
        openai_tools = [tool.to_openai_tool() for tool in (tools or [])]
        self._logger.info(f"openai_tools: {openai_tools}")
        _kwargs.update({
            "messages": messages,
            "tools": openai_tools,
            **kwargs,
            **{"stream": True, "stream_options": {"include_usage": True}}
        })

        completion = await self.client.chat.completions.create(**_kwargs)

        usage = None
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
                    self._logger.info(f"超出循环次数，结束循环 >>> count: {count}")
                    break
                elif not response.choices:
                    self._logger.info("流数据结束传输")
                    break

                model = response.model
                created_at = response.created
                response_id = response.id

                if response.usage:
                    usage = response.usage

                ai_output = response.choices[0].delta
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
                        self._logger.info(f"current tool_calls >>> {final_tool_calls}")

                        # 实时生成chunk（即使字段不完整）
                        yield ToolCallChunk(
                            response_id=response.id,
                            tool_call_id=tool_id,
                            tool_name=tool_call.function.name or "",
                            arguments=tool_call.function.arguments or "",
                            created_at=created_at
                        )

                else:
                    content = ai_output.content
                    if content:
                        final_text += content
                        yield TextChunk(response_id=response.id, text=content, created_at=created_at)

                # 如果返回携带了结束信号，则退出循环
                if response.choices[0].finish_reason:
                    self._logger.info(f"收到流式结束信号: {response.choices[0].finish_reason}")
                    break

            # 循环结束后立即释放资源
            await completion.close()  # 确保资源释放
            self._logger.debug("流式连接已关闭")
            
            # 生成最终结果
            if final_tool_calls:
                self._logger.info(f"final_tool_calls >>> {final_tool_calls}")
                for key, call_data in final_tool_calls.items():
                    yield ToolCallFinal(
                        response_id=response_id,
                        tool_call_id=key,
                        tool_name=call_data['name'].strip(),
                        arguments=call_data['arguments'].strip(),
                        created_at=call_data['created_at']
                    )

            if final_text:
                yield TextFinal(response_id=response_id, text=final_text, created_at=created_at)

            if usage:
                usage_dict = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens
                }
                yield UsageBlock(**usage_dict, response_id=response_id, provider=self.imitator, created_at=created_at)

        except asyncio.CancelledError:
            self._logger.warning("流式请求被取消")
