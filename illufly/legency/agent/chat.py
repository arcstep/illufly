from typing import List, Dict, Any, Union, Tuple

import hashlib
import asyncio

from ..rocksdb import default_rocksdb, IndexedRocksDB
from ..community import BaseVectorDB, BaseChat, normalize_messages
from ..mq import ServiceDealer, service_method
from ..mq.models import BlockType
from ..thread import Thread, HistoryMessage, QuestionBlock, AnswerBlock
from ..memory import KnowledgeGraph
from .utils import extract_json_text
from .models import (
    MemoryDomain,
    MemoryTopic,
    MemoryChunk,
    CHAT_THREAD_NO_RECENT,
    DOMAIN_MODEL,
    TOPIC_MODEL,
    CHUNK_MODEL
)

THREAD_MODEL = "thread"
MESSAGE_MODEL = "message"

class ChatAgent(ServiceDealer):
    """对话智能体"""

    def __init__(
        self,
        llm: BaseChat,
        summary_llm: BaseChat = None,
        db: IndexedRocksDB = None,
        vector_db: BaseVectorDB = None,
        group: str = None,
        runnable_tools: list = None,
        **kwargs
    ):
        self.llm = llm
        self.summary_llm = summary_llm or llm
        self.runnable_tools = runnable_tools
        if not group:
            group = self.llm.group
        service_name = getattr(self.llm, 'imitator', None) or self.llm.__class__.__name__
        super().__init__(group=group, service_name=service_name, **kwargs)

        self.db = db or default_rocksdb

        self.db.register_model(DOMAIN_MODEL, MemoryDomain)
        self.db.register_model(TOPIC_MODEL, MemoryTopic)
        self.db.register_model(CHUNK_MODEL, MemoryChunk)
        self.db.register_model(MESSAGE_MODEL, HistoryMessage)
        self.db.register_index(MESSAGE_MODEL, HistoryMessage, "created_with_thread")

        self.memory = KnowledgeGraph(
            llm=self.llm,
            docs_db=self.db,
            vector_db=vector_db
        )

        self._pending_lock = asyncio.Lock()

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
        thread_id: str = "",
        **kwargs
    ):
        """异步调用远程服务"""
        thread_id = thread_id or CHAT_THREAD_NO_RECENT
        normalized_messages = normalize_messages(messages)

        # 补充记忆
        await self._load_memory(user_id)

        converted_messages = await self._convert_messages(user_id, thread_id, normalized_messages)

        quesiton = None
        answer = None
        async for b in self.llm.chat(
            messages=converted_messages,
            runnable_tools=self.runnable_tools,
            **kwargs
        ):
            # 将部份消息类型持久化
            if b.block_type in [BlockType.QUESTION, BlockType.ANSWER, BlockType.TOOL]:
                b.user_id = user_id
                b.thread_id = thread_id

                # 归档问题和答案
                if b.block_type == BlockType.QUESTION:
                    question = b
                elif b.block_type == BlockType.ANSWER:
                    answer = b

                # 保存完整 CHUNK 到数据库
                self.db.update_with_indexes(
                    model_name=MESSAGE_MODEL,
                    key=HistoryMessage.get_key(b.user_id, b.thread_id, b.request_id, b.message_id),
                    value=b
                )

            yield b
        
        # 异步执行消息归档
        memory_fetch = asyncio.create_task(self._archive_messages(user_id, thread_id, question, answer))
        self._pending_tasks.add(memory_fetch)
        memory_fetch.add_done_callback(self._pending_tasks.discard)
    
    def _load_recent_messages(self, user_id: str, thread_id: str) -> str:
        """加载最近的消息"""
        if thread_id == CHAT_THREAD_NO_RECENT:
            return ""

        messages = []
        history_messages = sorted(
            self.db.values(
                prefix=HistoryMessage.get_thread_prefix(user_id, thread_id)
            ),
            key=lambda x: x.completed_at
        )
        for m in history_messages[-10:]:
            if m.role in ["user", "assistant", "tool"]:
                messages.append(m.to_message())
        self._logger.info(f"load_memory: {messages}")
        return "\n".join([str(m['role']) + ": " + str(m['content']) for m in messages])

    async def _convert_messages(self, user_id: str, thread_id: str, messages: List[Dict[str, Any]]) -> str:
        """补充消息中的记忆"""
        messages = messages or []
        recent_dialogue = "\n<details><summary>历史对话</summary>\n" + self._load_recent_messages(user_id, thread_id) + "\n</details>\n"

        query_texts = "\n".join([m['content'] for m in messages if m['role'] in ["user", "assistant"]])
        existing_kg = "\n<details><summary>已有知识</summary>\n" + await self.memory.query(query_texts, user_id, limit=20) + "\n</details>\n"   
        self._logger.info(f"existing_kg: {existing_kg}")

        if not recent_dialogue:
            self._logger.info(f"no memory")
            self._update_thread_title(user_id, thread_id, messages)

        self._logger.info(f"recent_dialogue: {recent_dialogue}")

        if messages and messages[0]['role'] == 'system':
            return [
                {
                    'role': 'system',
                    'content': messages[0]['content'] + existing_kg + recent_dialogue
                },
                *messages[1:]
            ]
        else:
            return [
                {'role': 'system', 'content': "你是一个AI助手，请根据已知知识回答问题。\n" + existing_kg + recent_dialogue},
                *messages
            ]

    def _update_thread_title(self, user_id: str, thread_id: str, messages: List[Dict[str, Any]]):
        """更新对话标题"""
        if not messages or thread_id == CHAT_THREAD_NO_RECENT:
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

    @service_method(name="list_memory", description="列出所有记忆")
    async def _list_memory(self, user_id: str):
        """列出所有记忆"""
        return list(self.memory.get_newest_triples(user_id))

    async def _load_memory(self, user_id: str):
        """加载记忆"""
        self._logger.info(f"加载记忆: {user_id}")
        await self.memory.load_for_user(user_id)

    async def _archive_messages(self, user_id: str, thread_id: str, question: QuestionBlock, answer: AnswerBlock):
        """从问答内容中提取内容做记忆归档"""
        AQ = f"问题：{question.text}\n答案：{answer.text}"
        self._logger.info(f"归档记忆: {AQ}")
        await self.memory.extract(AQ, user_id, limit=20)

