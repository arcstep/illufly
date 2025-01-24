from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union

import logging

from ..call import RemoteServer
from ..mq import Publisher, StreamingBlock, BlockType, TextChunk
from .contexts import ShortMemoryContext

class ChatBase(RemoteServer, ABC):
    """Base Chat Service

    按照多种维度，根据问题转换上下文环境：
    - 多轮对话
    - 工具回调
    - 概念清单
    - 思考方法
    - 思考习惯
    - 样本示例
    - 资料检索
    - 网络搜索
    - 数据集描述
    ...
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.context_managers = [
            ShortMemoryContext()
        ]

        self._logger = logging.getLogger(__name__)

        self.last_input = []
        self.last_output = []

    @abstractmethod
    async def _async_generate_from_llm(self, messages: Union[str, List[Dict[str, Any]]], thread_id: str, publisher: Publisher, **kwargs):
        """要求在子类中实现"""
        pass

    async def _async_handler(self, messages: Union[str, List[Dict[str, Any]]], thread_id: str, publisher: Publisher, **kwargs):
        """转换提问的问题"""

        # 规范化消息
        normalized_messages = self.normalize_messages(messages)

        # 处理消息上下文
        self._logger.info(f"Input messages from: {normalized_messages}")
        messages_with_context = self.handle_input_messages(normalized_messages)
        self.last_input = messages_with_context
        self._logger.info(f"last input: {messages_with_context}")

        # 调用 LLM 生成回答
        final_text = await self._async_generate_from_llm(messages_with_context, thread_id, publisher, **kwargs)
        self.last_output = final_text
        self._logger.info(f"last output: {final_text}")

        # 处理输出消息
        self.handle_output_messages([{"role": "assistant", "content": final_text}])
        self._logger.info(f"now output: {self.context_managers[0].history}")

        return final_text

    def normalize_messages(self, messages: Union[str, List[Dict[str, Any]]]):
        """规范化消息"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        return messages

    def handle_input_messages(self, messages: List[Dict[str, Any]]):
        """处理输入消息"""
        context_messages = []
        for m in self.context_managers:
            context_messages.extend(m.handle_input_messages(messages))
        return context_messages

    def handle_output_messages(self, messages: List[Dict[str, Any]]):
        """处理输出消息"""
        for context_manager in self.context_managers:
            context_manager.handle_output_messages(messages)
