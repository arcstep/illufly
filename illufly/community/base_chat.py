from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union, Tuple
from datetime import datetime

import logging
import json
import uuid

from ..mq.models import StreamingBlock, BlockType
from ..thread.models import QueryBlock, AnswerBlock, ToolBlock
from .base_tool import BaseTool
from .models import TextFinal, ToolCallFinal, TextChunk

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
            m['content'] = m.get('content', '')
            new_messages.append(m)
    return new_messages

class BaseChat(ABC):
    """Base Chat Generator"""
    def __init__(self, logger: logging.Logger = None):
        self._logger = logger or logging.getLogger(__name__)
        self.group = self.__class__.__name__

    def create_request_id(self):
        """创建请求ID"""
        return f"{self.__class__.__name__}.{uuid.uuid4().hex[:8]}"

    async def list_models(self) -> List[str]:
        """列出所有模型"""
        return []

    @abstractmethod
    async def generate(self, messages: Union[str, List[Dict[str, Any]]], **kwargs):
        """异步生成响应"""
        pass

    async def call_tool(self, request_id: str, tool_calls: List[ToolCallFinal], tools: List[BaseTool]) -> list:
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
                
                tool_block_resp.text = text_final or '工具执行完毕，但没有任何结果'
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
        max_turns: int = 10,
        runnable_tools: list = None,
        **kwargs
    ) -> list:
        """
        自动化对话流程
        :param messages: 初始消息列表
        :param runnable_tools: 只在没有使用 kwargs['tools'] 参数的情况下生效
        :param max_turns: 单次推理最大对话轮次
        :return: 最终消息历史
        """
        conv_messages = normalize_messages(messages)
        tools_callable = [] if kwargs.get("tools") else (runnable_tools or [])
        tools = kwargs.pop("tools", None) or [t.to_openai() for t in tools_callable]
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
            logger.info(f"conv_messages: {conv_messages}")
            # 如果 tools 为空，则不传递 tools 参数：
            #   Qwen 接口不兼容 []
            try:
                async for chunk in self.generate(conv_messages, tools=(tools or None), **kwargs):
                    answer_created_at = query_completed_at
                    answer_completed_at = datetime.now().timestamp()
                    if isinstance(chunk, TextFinal):
                        text_finals.append(chunk)
                    elif isinstance(chunk, ToolCallFinal):
                        tool_calls.append(chunk)

                    yield chunk

            except Exception as e:
                answer_created_at = query_completed_at
                answer_completed_at = datetime.now().timestamp()
                logger.error(f"生成模型响应失败: {e}")
                error_chunk = TextChunk(
                    response_id=uuid.uuid4().hex[:8],
                    text=f"生成模型响应失败: {str(e)}",
                    model="unknown",
                    finish_reason="stop",
                    created_at=datetime.now().timestamp()
                )
                yield error_chunk

                error_chunk.block_type = BlockType.TEXT_FINAL
                yield error_chunk

                text_finals.append(error_chunk)

            # 准备基于工具自动调用结果的下一轮对话
            conv_messages.append({
                "role": "assistant",
                "tool_calls": [chunk.content for chunk in tool_calls] or [],
                "content": "\n".join([chunk.content for chunk in text_finals])
            })
            # 生成回答流事件
            yield AnswerBlock(
                request_id=request_id,
                response_id=uuid.uuid4().hex[:8],
                message_id=uuid.uuid4().hex[:8],
                message_type="text",
                role=conv_messages[-1]["role"],
                text=conv_messages[-1].get("content", ""),
                tool_calls=conv_messages[-1].get("tool_calls", []),
                created_at=answer_created_at,
                completed_at=answer_completed_at
            )

            # 如果没有工具调用，或者虽然有工具回调返回但无内置的工具立即调用，则结束对话，等待对话客户端处理
            if not tool_calls or not tools_callable:
                return            

            # 执行工具调用
            self._logger.info(f"执行工具调用: {[t.content for t in tool_calls]}")
            async for tool_resp in self.call_tool(request_id, tool_calls, tools=tools_callable):
                self._logger.info(f"执行工具调用结果: {tool_resp.block_type} >> {tool_resp.text}")
                if isinstance(tool_resp, ToolBlock):
                    conv_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_resp.tool_id,
                        "content": tool_resp.text
                    })
                yield tool_resp

            # 重新调用模型
            query_created_at = datetime.now().timestamp()
            self._logger.info(f"重新调用模型: {conv_messages}")

