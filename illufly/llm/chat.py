from typing import List, Dict, Any, Union
from pydantic import BaseModel, Field

from ..rocksdb import default_rocksdb, IndexedRocksDB
from .base import LiteLLM
from .models import ChunkType, DialougeChunk, ToolCalling, MemoryQA
from .memory import Memory
from .retriever import ChromaRetriever

from datetime import datetime
import asyncio
import logging
logger = logging.getLogger(__name__)

class ChatAgent():
    """对话智能体"""
    def __init__(self, db: IndexedRocksDB=None, memory: Memory=None, **kwargs):
        self.llm = LiteLLM(**kwargs)
        self.db = db or default_rocksdb
        self.memory = memory or Memory(llm=self.llm, memory_db=self.db)

        self.recent_messages_count = 10
        DialougeChunk.register_indexes(self.db)

    async def chat(self, messages: List[Dict[str, Any]], model: str, user_id: str=None, thread_id: str=None, **kwargs):
        """对话

        对话核心流程：
        1. 加载历史 + 检索记忆
        2. 注入记忆 + 保存用户输入
        3. 并行执行：提取新记忆 + 对话补全
        """
        final_text = ""
        final_tool_calls = {}
        last_tool_call_id = None
        input_created_at = datetime.now().timestamp()

        if not messages:
            raise ValueError("messages 不能为空")

        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        
        # 1. 加载历史消息
        if not isinstance(messages, list):
            raise ValueError("messages 必须是形如 [{'role': 'user', 'content': '用户输入'}, ...] 的列表")
        else:
            history_messages = self._load_recent_messages(user_id, thread_id)
            if messages[0].get("role", None) == "system":
                messages = [messages[0], *history_messages, *messages[1:]]
            else:
                messages = [*history_messages, *messages]

        # 2. 加载并处理检索的记忆
        retrieved_memories = await self.memory.retrieve(messages, user_id)

        # 首先发送检索记忆事件
        if retrieved_memories:
            for memory in retrieved_memories:
                memory_chunk = DialougeChunk(
                    user_id=user_id,
                    thread_id=thread_id,
                    chunk_type=ChunkType.MEMORY_RETRIEVE,
                    role="assistant",
                    memory=memory
                )
                self.save_dialog_chunk(memory_chunk)
                yield memory_chunk.model_dump()

        # 将记忆转化为表格形式用于注入提示
        memory_table = ""
        if retrieved_memories:
            items = [f'|{m.topic}|{m.question}|{m.answer}|' for m in retrieved_memories]
            memory_table = f"\n\n|主题|问题|答案|\n|---|---|---|\n{chr(10).join(items)}\n"

        # 注入记忆到消息中
        messages = self.memory.inject(messages, memory_table)

        # 3. 保存用户输入（包含历史和记忆）
        dialog_chunk = DialougeChunk(
            user_id=user_id,
            thread_id=thread_id,
            chunk_type=ChunkType.USER_INPUT,
            input_messages=messages,
            created_at=input_created_at
        )
        self.save_dialog_chunk(dialog_chunk)

        # 4. 并行执行记忆提取和对话补全
        extract_task = asyncio.create_task(
            self.memory.extract(messages, model, memory_table, user_id)
        )

        logger.info(f"\nchat completion [{model}] >>> {messages}")

        # 5. 执行对话补全
        try:
            resp = await self.llm.acompletion(messages, model=model, stream=True, **kwargs)
        except Exception as e:
            logger.error(f"\nchat completion [{model}] >>> {messages}\n\nerror >>> {e}")
            return

        first_chunk = None
        async for chunk in resp:
            ai_output = chunk.choices[0].delta if chunk.choices else None
            if ai_output and ai_output.content:
                if not first_chunk:
                    first_chunk = DialougeChunk(
                        user_id=user_id,
                        thread_id=thread_id,
                        chunk_type=ChunkType.AI_DELTA,
                        output_text=ai_output.content
                    )
                else:
                    first_chunk.output_text = ai_output.content
                final_text += ai_output.content
                yield first_chunk.model_dump()

            elif ai_output and ai_output.tool_calls:
                for tool_call in ai_output.tool_calls:
                    tool_id = tool_call.id or last_tool_call_id                    
                    if tool_id:
                        last_tool_call_id = tool_id
                    if tool_id not in final_tool_calls:
                        final_tool_calls[tool_id] = ToolCalling(
                            tool_id=tool_id,
                            name="",
                            arguments=""
                        )
                    current = final_tool_calls[tool_id]
                    current.name += tool_call.function.name or ""
                    current.arguments += tool_call.function.arguments or ""

            else:
                # print(chunk)
                pass

        # 6. 保存 AI 输出
        if final_text:
            dialog_chunk = DialougeChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.AI_MESSAGE,
                output_text=final_text
            )
            self.save_dialog_chunk(dialog_chunk)

        if final_tool_calls:
            dialog_chunk = DialougeChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.AI_MESSAGE,
                tool_calls=list(final_tool_calls.values())
            )
            self.save_dialog_chunk(dialog_chunk)
            yield dialog_chunk.model_dump()

        # 7. 等待记忆提取完成并返回结果
        extracted_memories = await extract_task
        if extracted_memories:
            for memory in extracted_memories:
                memory_chunk = DialougeChunk(
                    user_id=user_id,
                    thread_id=thread_id,
                    chunk_type=ChunkType.MEMORY_EXTRACT,
                    memory=memory
                )
                self.save_dialog_chunk(memory_chunk)
                yield memory_chunk.model_dump()

    def save_dialog_chunk(self, chunk: DialougeChunk):
        """保存对话片段

        仅当用户ID和线程ID存在时，才保存对话片段
        """
        if chunk.user_id and chunk.thread_id:
            logger.info(f"\nsave_dialog_chunk >>> {chunk}")
            self.db.update_with_indexes(
                model_name=DialougeChunk.__name__,
                key=DialougeChunk.get_key(chunk.user_id, chunk.thread_id, chunk.dialouge_id),
                value=chunk
            )

    def load_history(self, user_id: str, thread_id: str, limit: int = 100):
        """加载历史对话"""
        resp = sorted(
            self.db.values(
                prefix=DialougeChunk.get_prefix(user_id, thread_id),
                limit=limit,
                reverse=True
            ),
            key=lambda x: x.created_at
        )
        messages = []
        for m in resp:
            if m.chunk_type == ChunkType.USER_INPUT:
                messages.append({
                    "role": "user",
                    "content": m.input_messages[-1]['content'],
                    "chunk_type": m.chunk_type.value,
                    "created_at": m.created_at,
                    "dialouge_id": m.dialouge_id
                })
            elif m.chunk_type == ChunkType.AI_MESSAGE:
                messages.append({
                    "role": "assistant",
                    "content": m.output_text,
                    "chunk_type": m.chunk_type.value,
                    "created_at": m.created_at,
                    "dialouge_id": m.dialouge_id
                })
            elif m.chunk_type == ChunkType.MEMORY_RETRIEVE:
                messages.append({
                    "role": "assistant", 
                    "chunk_type": m.chunk_type.value,
                    "memory": m.memory.model_dump() if m.memory else None,
                    "created_at": m.created_at,
                    "dialouge_id": m.dialouge_id
                })
            elif m.chunk_type == ChunkType.MEMORY_EXTRACT:
                messages.append({
                    "role": "assistant",
                    "chunk_type": m.chunk_type.value, 
                    "memory": m.memory.model_dump() if m.memory else None,
                    "created_at": m.created_at,
                    "dialouge_id": m.dialouge_id
                })
        return messages

    def _load_recent_messages(self, user_id: str=None, thread_id: str=None) -> str:
        """加载最近的消息"""
        if not user_id or not thread_id:
            return ""
        return self.load_history(user_id, thread_id, limit=self.recent_messages_count)
