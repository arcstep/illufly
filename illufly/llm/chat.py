from typing import List, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum

from ..rocksdb import default_rocksdb, IndexedRocksDB
from .base import LiteLLM

import time
import logging
logger = logging.getLogger(__name__)

class ToolCalling(BaseModel):
    tool_id: str = Field(default="", description="工具ID")
    name: str = Field(default="", description="工具名称")
    arguments: str = Field(default="", description="工具参数")

class ChunkType(Enum):
    USER_INPUT = "user_input"
    AI_DELTA = "ai_delta"
    AI_MESSAGE = "ai_message"

class DialougeChunk(BaseModel):
    user_id: str = Field(default="", description="用户ID")
    thread_id: str = Field(default="", description="线程ID")
    dialouge_id: str = Field(default="", description="对话ID")
    created_at: float = Field(default_factory=time.time, description="创建时间")
    chunk_type: ChunkType = Field(default=ChunkType.USER_INPUT, description="角色")
    input_messages: List[Dict[str, Any]] = Field(default=[], description="输入消息")
    output_text: str = Field(default="", description="输出消息")
    tool_calls: List[ToolCalling] = Field(default=[], description="工具调用")

    def model_dump(self):
        common_fields = {
            "user_id": self.user_id,
            "thread_id": self.thread_id,
            "dialouge_id": self.dialouge_id,
            "created_at": self.created_at,
        }
        if self.chunk_type == ChunkType.USER_INPUT:
            return {
                **common_fields,
                "chunk_type": self.chunk_type,
                "input_messages": self.input_messages,
            }
        elif self.chunk_type == ChunkType.AI_DELTA:
            return {
                **common_fields,
                "chunk_type": self.chunk_type,
                "output_text": self.output_text,
            }
        elif self.chunk_type == ChunkType.AI_MESSAGE:
            return {
                **common_fields,
                "chunk_type": self.chunk_type,
                "output_text": self.output_text,
                "tool_calls": [v.model_dump() for v in self.tool_calls],
            }
        else:
            raise ValueError(f"Invalid chunk type: {self.chunk_type}")

class ChatAgent():
    """对话智能体"""
    def __init__(self, history: IndexedRocksDB=None, **kwargs):
        self.llm = LiteLLM(**kwargs)
        self.history_db = history or default_rocksdb

    async def chat(self, messages: List[Dict[str, Any]], **kwargs):
        """对话"""
        final_tool_calls = {}
        last_tool_call_id = None
        resp = await self.llm.acompletion(messages, stream=True, **kwargs)
        async for chunk in resp:
            ai_output = chunk.choices[0].delta if chunk.choices else None
            if ai_output and ai_output.content:
                dialog_chunk = DialougeChunk(
                    chunk_type=ChunkType.AI_DELTA,
                    output_text=ai_output.content
                )
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

        dialog_chunk = DialougeChunk(
            chunk_type=ChunkType.AI_MESSAGE,
            tool_calls=list(final_tool_calls.values())
        )
        yield dialog_chunk.model_dump()
