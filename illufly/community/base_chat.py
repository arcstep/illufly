from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union

import logging
import json

from ..mq.models import ToolCallFinal, TextFinal
from .base_tool import BaseTool, ToolCallMessage

class BaseChat(ABC):
    """Base Chat Generator"""
    def __init__(self, logger: logging.Logger = None):
        self._logger = logger or logging.getLogger(__name__)

    @abstractmethod
    async def generate(self, messages: Union[str, List[Dict[str, Any]]], **kwargs):
        """异步生成响应"""
        pass

    async def call_tool(self, messages:  Union[str, List[Dict[str, Any]]], tool_calls: List[ToolCallFinal], tools: List[BaseTool]) -> list:
        """
        新版工具调用方法
        :param tools_callable: BaseTool实例列表
        """
        for call in tool_calls:
            # 查找匹配的工具实例
            tool = next((t for t in tools if t.name == call.tool_name), None)
            if not tool:
                continue

            try:
                # 参数解析与校验
                args = json.loads(call.arguments) if call.arguments else {}
                validated_args = tool.args_schema(**args)
                
                # 执行工具调用
                final_result = None
                async for resp in tool.call(**validated_args.model_dump()):
                    if isinstance(resp, ToolCallMessage):
                        resp.tool_call_id = call.tool_call_id
                        final_result = resp
                        yield resp
                
                if not final_result:
                    yield ToolCallMessage(
                        request_id=call.request_id,
                        model=call.model,
                        tool_call_id=call.tool_call_id,
                        text=f"工具执行错误: 没有返回结果",
                        created_at=call.created_at
                    )

            except json.JSONDecodeError as e:
                yield ToolCallMessage(
                    request_id=call.request_id,
                    model=call.model,
                    tool_call_id=call.tool_call_id,
                    text=f"参数解析失败: {str(e)}",
                    created_at=call.created_at
                )
            except Exception as e:
                yield ToolCallMessage(
                    request_id=call.request_id,
                    model=call.model,
                    tool_call_id=call.tool_call_id,
                    text=f"工具执行错误: {str(e)}",
                    created_at=call.created_at
                )

    async def chat(self, messages: Union[str, List[Dict[str, Any]]], tools: list = None, max_turns: int = 3) -> list:
        """
        自动化对话流程
        :param messages: 初始消息列表
        :param tools: 工具列表
        :param max_turns: 最大对话轮次
        :return: 最终消息历史
        """
        conv_messages = messages.copy()
        tools_callable = tools or []

        for _ in range(max_turns):
            # 生成模型响应
            tool_calls = []
            text_finals = []
            self._logger.info(f"当前的消息列表: {conv_messages}")
            async for chunk in self.generate(conv_messages, tools=tools):
                if isinstance(chunk, TextFinal):
                    text_finals.append(chunk)
                if isinstance(chunk, ToolCallFinal):
                    tool_calls.append(chunk)
                yield chunk

            # 如果没有工具调用则结束
            if not tool_calls:
                break
            
            conv_messages.append({
                "role": "assistant",
                "tool_calls": [chunk.content for chunk in tool_calls],
                "content": "\n".join([chunk.content for chunk in text_finals])
            })

            # 执行工具调用
            async for resp in self.call_tool(conv_messages, tool_calls, tools_callable):
                if isinstance(resp, ToolCallMessage):
                    conv_messages.append(resp.content)
                yield resp
