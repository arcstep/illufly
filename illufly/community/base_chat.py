from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union, Tuple
from datetime import datetime

import logging
import json
import uuid

from ..mq.models import StreamingBlock
from ..thread.models import QueryBlock, AnswerBlock, ToolBlock
from .base_tool import BaseTool
from .models import TextFinal, ToolCallFinal

logger = logging.getLogger(__name__)

def normalize_messages(messages: Union[str, List[str], List[Tuple[str, Any]], List[Dict[str, Any]]]):
    _messages = messages if isinstance(messages, list) else [messages]
    new_messages = []
    def raise_error_with_role(role: str):
        if role not in ["user", "assistant", "system", "tool"]:
            raise ValueError(f"Invalid message role: {role}")
    for m in _messages:
        if isinstance(m, str):
            new_messages.append({"role": "user", "content": m})
        elif isinstance(m, tuple):
            role = "assistant" if m[0] == "ai" else m[0]
            raise_error_with_role(role)
            new_messages.append({"role": role, "content": m[1]})
        else:
            if m['role'] == "ai":
                m['role'] = "assistant"
            raise_error_with_role(m['role'])
            new_messages.append(m)
    logger.info(f"normalize_messages: {new_messages}")
    return new_messages

class BaseChat(ABC):
    """Base Chat Generator"""
    def __init__(self, logger: logging.Logger = None):
        self._logger = logger or logging.getLogger(__name__)
        self.group = self.__class__.__name__.lower()

    def create_request_id(self):
        """创建请求ID"""
        return f"{self.__class__.__name__}.{uuid.uuid4().hex[:8]}"

    @abstractmethod
    async def generate(self, messages: Union[str, List[Dict[str, Any]]], **kwargs):
        """异步生成响应"""
        pass

    async def call_tool(self, request_id: str, messages: List[Dict[str, Any]], tool_calls: List[ToolCallFinal], tools: List[BaseTool]) -> list:
        """
        新版工具调用方法
        :param tools_callable: BaseTool实例列表
        """
        for call in tool_calls:
            # 返回结果
            tool_block_resp = ToolBlock(
                request_id=request_id,
                response_id=uuid.uuid4().hex[:8],
                message_id=uuid.uuid4().hex[:8],
                role="tool",
                message_type="text",
                text="",
                tool_id=call.tool_call_id,
                created_at=datetime.now().timestamp()
            )
            # 查找匹配的工具实例
            tool = next((t for t in tools if t.name == call.tool_name), None)
            if not tool:
                continue

            try:
                # 参数解析与校验
                args = json.loads(call.arguments) if call.arguments else {}
                validated_args = tool.args_schema(**args)
                
                # 执行工具调用
                text_final = ""
                async for resp in tool.call(**validated_args.model_dump()):
                    if isinstance(resp, TextFinal):
                        text_final += resp.text
                    yield resp
                
                if not text_final:
                    tool_block_resp.text = text_final
                    tool_block_resp.completed_at = datetime.now().timestamp()
                    yield tool_block_resp

            except json.JSONDecodeError as e:
                tool_block_resp.text = f"参数解析失败: {str(e)}"
                tool_block_resp.completed_at = datetime.now().timestamp()
                yield tool_block_resp

            except Exception as e:
                tool_block_resp.text = f"工具执行错误: {str(e)}"
                tool_block_resp.completed_at = datetime.now().timestamp()
                yield tool_block_resp

    async def chat(
        self,
        messages: Union[str, List[str], List[Tuple[str, Any]], List[Dict[str, Any]]],
        tools: list = None,
        max_turns: int = 3
    ) -> list:
        """
        自动化对话流程
        :param messages: 初始消息列表
        :param tools: 工具列表
        :param max_turns: 最大对话轮次
        :return: 最终消息历史
        """
        conv_messages = normalize_messages(messages)
        tools_callable = tools or []
        request_id = self.create_request_id()
        query_created_at = datetime.now().timestamp()
        query_completed_at = query_created_at

        # 记录查询消息
        text = ""
        images = []
        audios = []
        videos = []
        for m in conv_messages:
            if isinstance(m['content'], str):
                message_type = "text"
                text = m['content']
            else:
                message_type = "image"
                text = ""
                for chunk in m['content']:
                    if chunk["type"] == "text":
                        text += chunk["text"]
                    elif chunk["type"] == "image":
                        images.append(chunk["image_url"])
                    elif chunk["type"] == "audio":
                        audios.append(chunk["audio_url"])
                    elif chunk["type"] == "video":
                        videos.append(chunk["video_url"])
            yield QueryBlock(
                request_id=request_id,
                message_id=uuid.uuid4().hex[:8],
                role=m['role'],
                message_type=message_type,
                text=text,
                images=images,
                audios=audios,
                videos=videos,
                created_at=query_created_at,
                completed_at=query_completed_at
            )

        for _ in range(max_turns):
            # 生成模型响应
            tool_calls = []
            text_finals = []

            # 生成查询流事件
            async for chunk in self.generate(conv_messages, tools=tools):
                answer_created_at = query_completed_at
                answer_completed_at = datetime.now().timestamp()
                if isinstance(chunk, TextFinal):
                    text_finals.append(chunk)
                elif isinstance(chunk, ToolCallFinal):
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
            # 生成回答流事件
            yield AnswerBlock(
                request_id=request_id,
                response_id=uuid.uuid4().hex[:8],
                message_id=uuid.uuid4().hex[:8],
                message_type="text",
                role=conv_messages[-1]["role"],
                text=conv_messages[-1]["content"],
                tool_calls=conv_messages[-1]["tool_calls"],
                created_at=answer_created_at,
                completed_at=answer_completed_at
            )

            # 执行工具调用
            async for tool_resp in self.call_tool(request_id, conv_messages, tool_calls, tools_callable):
                if isinstance(tool_resp, ToolBlock):
                    conv_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_resp.tool_id,
                        "content": tool_resp.text
                    })
                yield tool_resp

            # 重新调用模型
            query_created_at = datetime.now().timestamp()

