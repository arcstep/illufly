from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union, Set

import logging

from ..io.rocksdict import default_rocksdb, IndexedRocksDB
from ..llm.memory.L0_QA import QAManager, QA, Message
from ..call import RemoteServer
from ..mq import Publisher, StreamingBlock, BlockType, TextChunk
from .system_template import SystemTemplate

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
    def __init__(
        self,
        user_id: str = None,
        db: IndexedRocksDB = None,
        levels: Set[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)

        self.user_id = user_id or "default"
        self.db = db or default_rocksdb

        self._levels = {"L0", "L1", "L2", "L3"} if levels is None else levels
        self._logger = logging.getLogger(__name__)
        self._l0_qa = QAManager(db=self.db, user_id=user_id)

        self.thread = None

        if "L0" in self._levels:
            last_thread = self._l0_qa.last_thread()
            if not last_thread:
                last_thread = self._l0_qa.create_thread()
            self.thread = last_thread

    # L0 相关属性和方法

    @property
    def all_threads(self):
        return self._l0_qa.all_threads() if "L0" in self._levels else []
    
    @property
    def thread_id(self):
        return self.thread.thread_id if "L0" in self._levels else None

    @property
    def history(self):
        return self._l0_qa.retrieve(self.thread_id) if "L0" in self._levels else []
    
    @property
    def history_messages(self):
        return [m.message_dict for m in self.history] if "L0" in self._levels else []

    @property
    def all_QAs(self):
        return self._l0_qa.all_QAs(self.thread_id) if "L0" in self._levels else []

    def new_thread(self):
        """创建一个新的对话"""
        self.thread = self._l0_qa.create_thread() if "L0" in self._levels else None
    
    def load_thread(self, thread_id: str):
        """从历史对话加载"""
        if "L0" in self._levels:
            thread = self._l0_qa.get_thread(thread_id)
            if not thread:
                raise ValueError(f"对话 {thread_id} 不存在")
            self.thread = thread

    # L1 相关属性和方法
    # L2 相关属性和方法
    # L3 相关属性和方法

    @abstractmethod
    async def _async_generate_from_llm(
        self,
        messages: Union[str, List[Dict[str, Any]]],
        request_id: str, # RemoteServer 要求的参数
        publisher: Publisher, # RemoteServer 要求的参数
        **kwargs
    ):
        """要求在子类中实现
        
        Args:
            messages: 输入消息
            request_id: 请求ID（RemoteServer 要求的参数）
            publisher: 发布者（RemoteServer 要求的参数）
            **kwargs: 其他用户自定义参数
        """
        pass

    async def _async_handler(
        self,
        messages: Union[str, List[Dict[str, Any]]],
        request_id: str, # RemoteServer 要求的参数
        publisher: Publisher, # RemoteServer 要求的参数
        template: SystemTemplate = None,
        **kwargs
    ):
        """转换提问的问题
        
        Args:
            messages: 输入消息
            request_id: 请求ID（RemoteServer 要求的参数）
            publisher: 发布者（RemoteServer 要求的参数）
            template: 系统模板
            **kwargs: 其他用户自定义参数
        """

        # 规范化消息
        normalized_messages = self.normalize_messages(messages)
        self._logger.info(f"normalized messages objects: {normalized_messages}")

        # 补充认知上下文
        patched_messages = self._l0_qa.retrieve(self.thread_id, messages=normalized_messages) if "L0" in self._levels else normalized_messages

        # 调用 LLM 生成回答
        messages_with_context = [m.message_dict for m in patched_messages]
        self._logger.info(f"last input: {messages_with_context}")
        final_text = await self._async_generate_from_llm(messages_with_context, request_id, publisher, **kwargs)
        self._logger.info(f"last output: {final_text}")

        # 处理输出消息
        if "L0" in self._levels:
            qa_messages = normalized_messages + [Message(role="assistant", content=final_text)]
            qa = QA(
                user_id=self.user_id,
                thread_id=self.thread_id,
                messages=qa_messages
            )
            self._l0_qa.add_QA(qa)

    def normalize_messages(self, messages: Union[str, List[Dict[str, Any]]]):
        """规范化消息"""
        _messages = messages if isinstance(messages, list) else [messages]
        return [Message.create(m) for m in _messages]

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
