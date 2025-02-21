from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union, Tuple
from pydantic import BaseModel, Field
from datetime import datetime

import uuid
import logging

from ..rocksdb import default_rocksdb, IndexedRocksDB
from ..community import BaseChat, normalize_messages
from ..mq import ServiceDealer, service_method
from ..mq.models import BlockType
from ..thread import HistoryMessage
from .memory import MemoryManager

MESSAGE_MODEL = "message"

class BaseAgent(ServiceDealer):
    """Base Agent"""
    def __init__(
        self,
        llm: BaseChat,
        db: IndexedRocksDB = None,
        group: str = None,
        tools: list = None,
        **kwargs
    ):
        self.llm = llm
        self.tools = tools
        if not group:
            group = self.llm.group
        super().__init__(group=group, **kwargs)

        self.db = db or default_rocksdb
        self.db.register_model(MESSAGE_MODEL, HistoryMessage)
        self.db.register_index(MESSAGE_MODEL, HistoryMessage, "created_with_thread")

    @service_method(name="chat", description="对话服务")
    async def _chat(
        self,
        messages: Union[str, List[str], List[Dict[str, Any]], List[Tuple[str, Any]]],
        user_id: str = "default",
        thread_id: str = "default",
        **kwargs
    ):
        """异步调用远程服务"""
        normalized_messages = normalize_messages(messages)

        # 补充消息
        patched_messages = self.patch_messages(normalized_messages)

        async for b in self.llm.chat(
            messages=patched_messages,
            tools=self.tools,
            **kwargs
        ):
            # 将部份消息类型持久化
            if b.block_type in [BlockType.QUERY, BlockType.ANSWER, BlockType.TOOL]:
                b.user_id = user_id
                b.thread_id = thread_id

                # 保存完整 CHUNK 到数据库
                self.db.update_with_indexes(
                    model_name=MESSAGE_MODEL,
                    key=HistoryMessage.get_key(b.user_id, b.thread_id, b.request_id, b.message_id),
                    value=b
                )

            yield b

    def patch_messages(self, messages: List[Dict[str, Any]]):
        """从记忆中补充消息"""
        return messages

class ChatAgent(BaseAgent):
    """Chat Agent"""
    def __init__(
        self,
        memory_manager: MemoryManager = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.memory_manager = memory_manager

    def patch_messages(self, messages: List[Dict[str, Any]]):
        """补充消息中的记忆"""

        memory_messages = self.memory_manager.load_memory(user_id, thread_id, messages) if self.memory_manager else []
        if memory_messages:
            system_message = messages[0] if messages[0]['role'] == 'system' else {"role": "system", "content": ""}
            system_message['content'] += "<memory>\n\n" + "\n".join([m['content'] for m in memory_messages] + "</memory>")

            if not messages[0]['role'] == 'system':
                messages.insert(0, system_message)

        return messages
