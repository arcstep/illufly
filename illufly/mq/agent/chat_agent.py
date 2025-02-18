from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

import uuid
import logging
from ...rocksdb import default_rocksdb, IndexedRocksDB
from ..memory.utils import generate_short_id
from ..memory import Message, SimpleMessage, MemoryManager
from ..service import ServiceDealer
from ..llm.chat_base import ChatBase

THREAD_MODEL = "thread"
MESSAGE_MODEL = "message"

class Thread(BaseModel):
    """连续对话跟踪"""
    @classmethod
    def get_user_prefix(cls, user_id: str):
        return f"thread-{user_id}"

    @classmethod
    def get_key(cls, user_id: str, thread_id: str):
        return f"{cls.get_user_prefix(user_id)}-{thread_id}"

    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(default_factory=generate_short_id, description="对话ID")
    title: str = Field(default="", description="对话标题")
    created_at: datetime = Field(default_factory=datetime.now, description="对话创建时间")

class ChatAgent(ServiceDealer):
    """Chat Agent
    """
    def __init__(
        self,
        llm: ChatBase,
        db: IndexedRocksDB = None,
        memory_manager: MemoryManager = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.llm = llm

        self.db = db or default_rocksdb
        self.memory_manager = memory_manager

        self.db.register_model(THREAD_MODEL, Thread)
        self.db.register_model(MESSAGE_MODEL, Message)
        self.db.register_index(THREAD_MODEL, "user_id")

    @ServiceDealer.service_method(name="all_threads", description="获取所有对话")
    def all_threads(self, user_id: str):
        return self.db.values(
            prefix=Thread.get_user_prefix(user_id)
        )
    
    @ServiceDealer.service_method(name="new_thread", description="创建新对话")
    def new_thread(self, user_id: str):
        """创建新对话"""
        new_thread = Thread(user_id=user_id)
        self.db.update_with_indexes(
            model_name=THREAD_MODEL,
            key=new_thread.get_key(),
            value=new_thread
        )
        return new_thread
    
    @ServiceDealer.service_method(name="load_messages", description="加载历史对话")
    def load_messages(self, user_id: str, thread_id: str):
        """加载历史对话"""
        return self.db.values(
            prefix=Message.get_thread_prefix(user_id, thread_id)
        )

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
        message_id = generate_short_id()  # 初始化message_id
        buffer = []  # 新增缓冲区用于暂存CHUNK消息
        created_at = datetime.now(datetime.UTC)
        completed_at = created_at
        request_id = self.create_request_id()

        # 补充消息中的记忆
        memory_messages = self.memory_manager.load_memory(user_id, thread_id, normalized_messages) if self.memory_manager else []
        if memory_messages:
            system_message = normalized_messages[0] if normalized_messages[0].role == 'system' else SimpleMessage(role="system", content="")
            system_message.content += "<memory>\n\n" + "\n".join([m.content for m in memory_messages] + "</memory>")

            if not normalized_messages[0].role == 'system':
                normalized_messages.insert(0, system_message)

        async for b in await self.llm.generate(
            messages=normalized_messages,
            **kwargs
        ):
            # 处理消息ID和内容
            if b.block_type == BlockType.TEXT_CHUNK:
                final_text += b.text
                current_message_id = message_id
                buffer.append(b)  # 将CHUNK消息暂存到缓冲区
            else:
                # 处理缓冲区中的CHUNK消息
                if buffer:
                    # 创建完整的CHUNK消息对象
                    completed_at = datetime.now(datetime.UTC)
                    chunk_message = Message(
                        user_id=self.user_id,
                        thread_id=self.thread_id,
                        request_id=request_id,
                        message_id=message_id,
                        role=buffer[0].role,  # 使用第一个CHUNK的role
                        content=final_text,
                        created_at=created_at,
                        completed_at=completed_at
                    )
                    # 保存完整CHUNK到数据库
                    self.db.update_with_indexes(
                        model_name=MESSAGE_MODEL,
                        key=Message.get_key(self.user_id, self.thread_id, message_id),
                        value=chunk_message
                    )
                    buffer.clear()  # 清空缓冲区
                    final_text = ""
                
                # 处理非CHUNK消息
                current_message_id = generate_short_id()                
                message_id = current_message_id
                created_at = datetime.now(datetime.UTC)
                completed_at = created_at
                message = Message(
                    user_id=self.user_id,
                    thread_id=self.thread_id,
                    message_id=current_message_id,
                    role=b.role,
                    content=b.text
                )
                # 立即保存非CHUNK消息
                self.db.update_with_indexes(
                    model_name=MESSAGE_MODEL,
                    key=Message.get_key(self.user_id, self.thread_id, current_message_id),
                    value=message
                )
                yield message

            # 实时yield CHUNK消息（不立即保存）
            if b.block_type == BlockType.TEXT_CHUNK:
                yield Message(
                    user_id=self.user_id,
                    thread_id=self.thread_id,
                    message_id=current_message_id,
                    role=b.role,
                    content=final_text  # 包含当前累积的完整内容
                )

        # 处理循环结束后的剩余CHUNK消息
        if buffer:
            completed_at = datetime.now(datetime.UTC)
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

        # 写入认知上下文
        output_messages = [Message(role="assistant", content=final_text)]
        self.after_call(normalized_messages, output_messages, request_id=request_id, **kwargs)

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
