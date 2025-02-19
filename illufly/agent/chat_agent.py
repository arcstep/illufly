from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

import uuid
import logging

from ..rocksdb import default_rocksdb, IndexedRocksDB
from ..community import BaseChat
from ..service import ServiceDealer
from .thread.models import Message, SimpleMessage
from .memory import MemoryManager

MESSAGE_MODEL = "message"

def generate_short_id():
    return uuid.uuid4().hex[:8]

def generate_now():
    return datetime.now(datetime.UTC)

class BaseAgent(ServiceDealer):
    """Base Agent"""
    def __init__(
        self,
        llm: BaseChat,
        db: IndexedRocksDB = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.llm = llm

        self.db = db or default_rocksdb
        self.db.register_model(MESSAGE_MODEL, Message)

    @ServiceDealer.service_method(name="chat", description="对话服务")
    async def _chat(
        self,
        user_id: str,
        thread_id: str,
        messages: Union[str, List[Dict[str, Any]]],
        **kwargs
    ):
        """异步调用远程服务"""
        normalized_messages = self.normalize_messages(messages)

        # 收集最终文本
        final_text = ""
        message_id = generate_short_id()  # 初始化 message_id
        buffer = []  # 新增缓冲区用于暂存 CHUNK 消息
        created_at = generate_now()
        completed_at = created_at
        request_id = self.create_request_id()

        # 补充消息
        patched_messages = self.patch_messages(normalized_messages)

        async for b in await self.llm.generate(
            messages=patched_messages,
            **kwargs
        ):
            # 处理消息 ID 和内容
            if b.block_type == BlockType.TEXT_CHUNK:
                final_text += b.text
                current_message_id = message_id
                buffer.append(b)  # 将 CHUNK 消息暂存到缓冲区
            else:
                # 处理缓冲区中的 CHUNK 消息
                if buffer:
                    # 创建完整的 CHUNK 消息对象
                    completed_at = generate_now()
                    chunk_message = Message(
                        user_id=self.user_id,
                        thread_id=self.thread_id,
                        request_id=request_id,
                        message_id=message_id,
                        role=buffer[0].role,  # 使用第一个 CHUNK 的 role
                        content=final_text,
                        created_at=created_at,
                        completed_at=completed_at
                    )
                    # 保存完整 CHUNK 到数据库
                    self.db.update_with_indexes(
                        model_name=MESSAGE_MODEL,
                        key=Message.get_key(self.user_id, self.thread_id, message_id),
                        value=chunk_message
                    )
                    buffer.clear()  # 清空缓冲区
                    final_text = ""
                
                # 处理非 CHUNK 消息
                current_message_id = generate_short_id()                
                message_id = current_message_id
                created_at = generate_now()
                completed_at = created_at
                message = Message(
                    user_id=self.user_id,
                    thread_id=self.thread_id,
                    message_id=current_message_id,
                    role=b.role,
                    content=b.text
                )
                # 立即保存非 CHUNK 消息
                self.db.update_with_indexes(
                    model_name=MESSAGE_MODEL,
                    key=Message.get_key(self.user_id, self.thread_id, current_message_id),
                    value=message
                )
                yield message

            # 实时 yield CHUNK 消息（不立即保存）
            if b.block_type == BlockType.TEXT_CHUNK:
                yield Message(
                    user_id=self.user_id,
                    thread_id=self.thread_id,
                    message_id=current_message_id,
                    role=b.role,
                    content=final_text  # 包含当前累积的完整内容
                )

        # 处理循环结束后的剩余 CHUNK 消息
        if buffer:
            completed_at = generate_now()
            chunk_message = Message(
                user_id=self.user_id,
                thread_id=self.thread_id,
                message_id=message_id,
                role=buffer[0].role,
                content=final_text,
                created_at=created_at,
                completed_at=completed_at
            )
            self.db.update_with_indexes(
                model_name=MESSAGE_MODEL,
                key=Message.get_key(self.user_id, self.thread_id, message_id),
                value=chunk_message
            )

    def normalize_messages(self, messages: Union[str, List[Dict[str, Any]]]):
        """规范化消息"""
        self._logger.info(f"messages: {messages}")
        _messages = messages if isinstance(messages, list) else [messages]
        return [Message.create(m) for m in _messages]

    def create_request_id(self, request_id: str = ""):
        """创建请求ID"""
        if not request_id:
            request_id = f"{self.__class__.__name__}.{uuid.uuid4()}"
        return request_id

    def patch_messages(self, messages: List[Message]):
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

    def patch_messages(self, messages: List[Message]):
        """补充消息中的记忆"""

        memory_messages = self.memory_manager.load_memory(user_id, thread_id, messages) if self.memory_manager else []
        if memory_messages:
            system_message = messages[0] if messages[0].role == 'system' else SimpleMessage(role="system", content="")
            system_message.content += "<memory>\n\n" + "\n".join([m.content for m in memory_messages] + "</memory>")

            if not messages[0].role == 'system':
                messages.insert(0, system_message)

        return messages
