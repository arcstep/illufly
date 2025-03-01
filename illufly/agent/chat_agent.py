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
from ..thread import HistoryMessage, Thread
from .memory import MemoryManager

THREAD_MODEL = "thread"
MESSAGE_MODEL = "message"
CHAT_DIRECTLY_THREAD_ID = "chat_directly_thread"

class BaseAgent(ServiceDealer):
    """Base Agent"""
    def __init__(
        self,
        llm: BaseChat,
        db: IndexedRocksDB = None,
        group: str = None,
        runnable_tools: list = None,
        **kwargs
    ):
        self.llm = llm
        self.runnable_tools = runnable_tools
        if not group:
            group = self.llm.group
        super().__init__(group=group, **kwargs)

        self.db = db or default_rocksdb
        self.db.register_model(MESSAGE_MODEL, HistoryMessage)
        self.db.register_index(MESSAGE_MODEL, HistoryMessage, "created_with_thread")

    @service_method(name="models", description="列出所有模型")
    async def _list_models(self):
        """列出所有模型"""
        all_models = await self.llm.list_models()
        self._logger.info(f"列出所有模型: {all_models[:5]}...等 {len(all_models)} 个模型")
        return all_models

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

        # 补充记忆
        messages_with_memory = self.patch_memory(user_id, thread_id, normalized_messages)
        self._logger.info(f"messages_with_memory: {messages_with_memory}")

        async for b in self.llm.chat(
            messages=messages_with_memory,
            runnable_tools=self.runnable_tools,
            **kwargs
        ):
            # 将部份消息类型持久化
            if b.block_type in [BlockType.QUESTION, BlockType.ANSWER, BlockType.TOOL]:
                b.user_id = user_id
                b.thread_id = thread_id

                # 保存完整 CHUNK 到数据库
                self.db.update_with_indexes(
                    model_name=MESSAGE_MODEL,
                    key=HistoryMessage.get_key(b.user_id, b.thread_id, b.request_id, b.message_id),
                    value=b
                )

            yield b
    
    def patch_memory(self, user_id: str, thread_id: str, messages: List[Dict[str, Any]]) -> str:
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

    def patch_memory(self, user_id: str, thread_id: str, messages: List[Dict[str, Any]]) -> str:
        """补充消息中的记忆"""
        messages = messages or []
        memory = self.memory_manager.load_memory(user_id, thread_id, messages) if self.memory_manager else []        

        if not memory:
            self._logger.info(f"no memory")
            self.update_thread_title(user_id, thread_id, messages)
            return messages

        self._logger.info(f"memory: {memory}")

        if messages and messages[0]['role'] == 'system':
            return [
                {
                    'role': 'system',
                    'content': messages[0]['content'] + f'\n\n<details><summary>Memory</summary>\n\n{memory}\n\n</details>'
                },
                *messages[1:]
            ]
        else:
            return [
                {'role': 'system', 'content': memory},
                *messages
            ]

    def update_thread_title(self, user_id: str, thread_id: str, messages: List[Dict[str, Any]]):
        """更新对话标题"""
        if not messages or thread_id == CHAT_DIRECTLY_THREAD_ID:
            return
        
        for m in messages:
            if m['role'] == 'user' and isinstance(m['content'], str):
                title = m['content'][:20] + ("..." if len(m['content']) > 20 else "")
                break
            elif m['role'] == 'assistant' and isinstance(m['content'], dict) and m['content'].get('type') == 'text':
                title = m['content']['text'][:20] + ("..." if len(m['content']['text']) > 20 else "")
                break

        thread = self.db[Thread.get_key(user_id, thread_id)] or Thread(user_id=user_id, thread_id=thread_id)
        if not thread.title:
            thread.title = title
            self.db.update_with_indexes(
                model_name=THREAD_MODEL,
                key=Thread.get_key(user_id, thread_id),
                value=thread
            )
            self._logger.info(f"update thread title: {title}")
