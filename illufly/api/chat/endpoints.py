from fastapi import FastAPI, Depends, Response, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Optional, Callable, Union, Tuple
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from enum import Enum

import uuid
import logging
import json

from ...mq.service import ClientDealer
from ...community.models import BlockType
from ..models import Result, HttpMethod
from ..http import handle_errors
from ..auth import require_user, TokensManager, TokenClaims
from ..models import Result, OpenaiRequest
from ...community.models import TextChunk

THREAD = {
    "all_threads": "ThreadManagerDealer.all_threads",
    "new_thread": "ThreadManagerDealer.new_thread",
    "load_messages": "ThreadManagerDealer.load_messages",
}

def create_chat_endpoints(
    app: FastAPI,
    zmq_client: ClientDealer = None,
    tokens_manager: TokensManager = None,
    prefix: str="/api",
    logger: logging.Logger = None
) -> Dict[str, Tuple[HttpMethod, str, Callable]]:
    """创建认证相关的API端点
    
    Returns:
        Dict[str, Tuple[HttpMethod, str, Callable]]: 
            键为路由名称，
            值为元组 (HTTP方法, 路由路径, 处理函数)
    """

    logger = logging.getLogger(__name__)

    @handle_errors()
    async def all_threads(
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """获取所有连续对话线程"""
        threads = await zmq_client.invoke(THREAD["all_threads"], user_id=token_claims['user_id'])
        return threads[0] or []

    @handle_errors()
    async def new_thread(
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """创建新的连续对话线程"""
        result = await zmq_client.invoke(THREAD["new_thread"], user_id=token_claims['user_id'])
        return result[0] or {}

    @handle_errors()
    async def load_messages(
        thread_id: str,
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """获取连续对话线程的消息"""
        messages = await zmq_client.invoke(
            THREAD["load_messages"],
            user_id=token_claims['user_id'],
            thread_id=thread_id
        )
        return messages[0] or []

    @handle_errors()
    async def models(
        imitator: str = "OPENAI",
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """获取模型列表"""
        models = await zmq_client.invoke(f"{imitator}.models")
        return models[0] or []

    class ChatRequest(OpenaiRequest):
        """聊天请求"""
        thread_id: str = Field(..., description="线程ID")
        imitator: str = Field(default="OPENAI", description="模仿者")

    @handle_errors()
    async def chat(
        chat_request: ChatRequest,
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """与大模型对话"""
        async def stream_response():
            async for chunk in zmq_client.stream(
                f"{chat_request.imitator}.chat",
                user_id=token_claims['user_id'],
                thread_id=chat_request.thread_id,
                **chat_request.model_dump(exclude={"thread_id", "imitator"})
            ):
                if getattr(chunk, 'block_type', None) in [BlockType.TEXT_CHUNK, BlockType.QUESTION]:
                    if chunk.block_type == BlockType.QUESTION:
                        block_type = "question"
                        message_type = "text"
                        role = chunk.role or "user"
                    else:
                        block_type = "answer"
                        message_type = chunk.block_type
                        role = chunk.role or "assistant"
                    message = {
                        "service_name": chunk.service_name,
                        "block_type": block_type,
                        "role": role,
                        "message_type": message_type,
                        "message_id": chunk.message_id,
                        "text": chunk.text,
                        "created_at": chunk.created_at,
                        "completed_at": chunk.completed_at,
                    }
                    yield f'data: {json.dumps(message, ensure_ascii=False)}\n\n'

            # 结束标记
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            content=stream_response(),
            media_type="text/event-stream",
            headers={
                "X-Accel-Buffering": "no",  # 关键头
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache"
            }
        )

    return [
        (HttpMethod.POST, f"{prefix}/chat/threads", new_thread),
        (HttpMethod.GET,  f"{prefix}/chat/threads", all_threads),
        (HttpMethod.GET,  f"{prefix}/chat/thread/{{thread_id}}/messages", load_messages),
        (HttpMethod.GET,  f"{prefix}/chat/models", models),
        (HttpMethod.POST, f"{prefix}/chat/complete", chat),
    ]
