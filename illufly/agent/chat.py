from typing import List, Dict, Any, Union, Tuple

import json
import hashlib
import asyncio

from ..rocksdb import default_rocksdb, IndexedRocksDB
from ..community import BaseChat, normalize_messages
from ..mq import ServiceDealer, service_method
from ..mq.models import BlockType
from ..thread import Thread, HistoryMessage, QuestionBlock, AnswerBlock
from ..prompt import PromptTemplate
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
        db: IndexedRocksDB = None,
        group: str = None,
        runnable_tools: list = None,
        **kwargs
    ):
        self.llm = llm
        self.runnable_tools = runnable_tools
        if not group:
            group = self.llm.group
        super().__init__(group=group, service_name=getattr(self.llm, 'imitator', '__class__.__name__'), **kwargs)

        self.db = db or default_rocksdb

        self.db.register_model(DOMAIN_MODEL, MemoryDomain)
        self.db.register_model(TOPIC_MODEL, MemoryTopic)
        self.db.register_model(CHUNK_MODEL, MemoryChunk)
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
        thread_id: str = "",
        **kwargs
    ):
        """异步调用远程服务"""
        thread_id = thread_id or CHAT_THREAD_NO_RECENT
        normalized_messages = normalize_messages(messages)

        # 补充记忆
        converted_messages = self._convert_messages(user_id, thread_id, normalized_messages)

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
        fetch_summary = asyncio.create_task(self._archive_messages(user_id, thread_id, question, answer))
        self._pending_tasks.add(fetch_summary)
        fetch_summary.add_done_callback(self._pending_tasks.discard)
    
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

    def _convert_messages(self, user_id: str, thread_id: str, messages: List[Dict[str, Any]]) -> str:
        """补充消息中的记忆"""
        messages = messages or []
        recent_dialogue = self._load_recent_messages(user_id, thread_id)        

        if not recent_dialogue:
            self._logger.info(f"no memory")
            self._update_thread_title(user_id, thread_id, messages)
            return messages

        self._logger.info(f"recent_dialogue: {recent_dialogue}")

        if messages and messages[0]['role'] == 'system':
            return [
                {
                    'role': 'system',
                    'content': messages[0]['content'] + f'\n\n<details><summary>Memory</summary>\n\n{recent_dialogue}\n\n</details>'
                },
                *messages[1:]
            ]
        else:
            return [
                {'role': 'system', 'content': recent_dialogue},
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

    @service_method(name="list_memory_topics", description="列出所有记忆主题")
    async def _list_memory_topics(self, user_id: str):
        """列出所有记忆主题"""
        topics = self.db.values(
            prefix=MemoryTopic.get_user_prefix(user_id)
        )
        return topics
    
    @service_method(name="list_memory_chunks", description="列出所有记忆片段")
    async def _list_memory_chunks(self, user_id: str, topic_id: str):
        """列出所有记忆片段"""
        chunks = self.db.values(
            prefix=MemoryChunk.get_user_prefix(user_id, topic_id)
        )
        return chunks

    async def _create_memory_topic(self, user_id: str, thread_id: str, title: str, summary: str = None):
        """创建记忆主题"""
        topic = MemoryTopic(
            user_id=user_id,
            thread_id=thread_id,
            title=title,
            summary=summary
        )
        self.db.update_with_indexes(TOPIC_MODEL, MemoryTopic.get_key(user_id, thread_id, topic.topic_id), topic)
        return topic
    
    async def _create_memory_chunk(self, user_id: str, thread_id: str, topic_id: str, question: str, answer: str):
        """创建记忆片段"""
        chunk = MemoryChunk(
            user_id=user_id,
            thread_id=thread_id,
            topic_id=topic_id,
            question=question,
            answer=answer)
        self.db.update_with_indexes(CHUNK_MODEL, MemoryChunk.get_key(user_id, thread_id, topic_id, chunk.chunk_id), chunk)
        return chunk

    async def _archive_messages(self, user_id: str, thread_id: str, question: QuestionBlock, answer: AnswerBlock):
        """从问答内容中提取内容做记忆归档"""
        if not question or not answer:
            return

        template = PromptTemplate(template_id="summary")
        system_prompt = template.format({
            "question": question.text,
            "answer": answer.text
        })
        user_prompt = "请直接输出json的解读结果。"

        # 构建消息
        messages = [
            {"role": 'system', "content": system_prompt},
            {"role": 'user', "content": user_prompt}
        ]

        # 将内容发送给zmq_dealer_name
        final_text = ""
        async for b in self.llm.chat(messages=messages):
            if b.block_type == BlockType.TEXT_FINAL:
                self._logger.info(f"archive result: {b.text}")
                final_text += b.text

        # 去除markdown格式
        final_text = final_text.strip()
        if final_text.startswith("```json"):
            final_text = final_text[len("```json"):].strip()
        if final_text.endswith("```"):
            final_text = final_text[:-len("```")]

        # 解析json
        if final_text:
            memory_chunk_dict = json.loads(final_text)
            topic = memory_chunk_dict.get("topic", None)
            question = memory_chunk_dict.get("question", None)
            answer = memory_chunk_dict.get("answer", None)

            if topic and question and answer:
                topic_id = hashlib.md5(topic.encode()).hexdigest()
                await self._create_memory_topic(user_id, thread_id, topic_id, topic)
                await self._create_memory_chunk(user_id, thread_id, topic_id, question, answer)
