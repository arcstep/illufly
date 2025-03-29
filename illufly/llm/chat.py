from typing import List, Dict, Any, Union
from pydantic import BaseModel, Field

from ..rocksdb import default_rocksdb, IndexedRocksDB
from .base import LiteLLM
from .models import ChunkType, DialougeChunk, ToolCalling

import logging
logger = logging.getLogger(__name__)

class ChatAgent():
    """对话智能体"""
    def __init__(self, db: IndexedRocksDB=None, **kwargs):
        self.llm = LiteLLM(**kwargs)
        self.db = db or default_rocksdb
        self.recent_messages_count = 10

        DialougeChunk.register_indexes(self.db)

    async def chat(self, messages: List[Dict[str, Any]], user_id: str=None, thread_id: str=None, **kwargs):
        """对话"""
        final_text = ""
        final_tool_calls = {}
        last_tool_call_id = None

        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        
        if not isinstance(messages, list):
            raise ValueError("messages 必须是形如 [{'role': 'user', 'content': '用户输入'}, ...] 的列表")
        else:
            history_messages = self._load_recent_messages(user_id, thread_id)
            if messages[0].get("role", None) == "system":
                messages = messages[:1] + history_messages + messages[1:]
            else:
                messages = history_messages + messages

        # 保存用户输入
        if messages:
            dialog_chunk = DialougeChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.USER_INPUT,
                input_messages=messages
            )
            self.save_dialog_chunk(dialog_chunk)

        resp = await self.llm.acompletion(messages, stream=True, **kwargs)
        async for chunk in resp:
            ai_output = chunk.choices[0].delta if chunk.choices else None
            if ai_output and ai_output.content:
                dialog_chunk = DialougeChunk(
                    chunk_type=ChunkType.AI_DELTA,
                    output_text=ai_output.content
                )
                final_text += ai_output.content
                yield dialog_chunk.model_dump()

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

        # 保存 AI 文本输出
        if final_text:
            dialog_chunk = DialougeChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.AI_MESSAGE,
                output_text=final_text
            )
            self.save_dialog_chunk(dialog_chunk)

        # 保存 AI 工具调用
        if final_tool_calls:
            dialog_chunk = DialougeChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.AI_MESSAGE,
                tool_calls=list(final_tool_calls.values())
            )
            self.save_dialog_chunk(dialog_chunk)
            yield dialog_chunk.model_dump()

    def save_dialog_chunk(self, chunk: DialougeChunk):
        """保存对话片段

        仅当用户ID和线程ID存在时，才保存对话片段
        """
        if chunk.user_id and chunk.thread_id:
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
                messages.append(m.input_messages[-1])
            elif m.chunk_type == ChunkType.AI_MESSAGE:
                messages.append({"role": "assistant", "content": m.output_text})
        return messages

    def _load_recent_messages(self, user_id: str=None, thread_id: str=None) -> str:
        """加载最近的消息"""
        if not user_id or not thread_id:
            return ""
        return self.load_history(user_id, thread_id, limit=self.recent_messages_count)
