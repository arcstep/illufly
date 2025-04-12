from fastapi import FastAPI, Depends, Response, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Optional, Callable, Union, Tuple
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from enum import Enum

import uuid
import logging
import json

from soulseal import TokenSDK
from ..models import Result, HttpMethod
from ..http import handle_errors
from ..models import Result, OpenaiRequest
from ...llm import ChatAgent, ThreadManager
from ...envir import get_env

def create_chat_endpoints(
    app: FastAPI,
    token_sdk: TokenSDK,
    agent: ChatAgent,
    thread_manager: ThreadManager,
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
    require_user = token_sdk.get_auth_dependency(logger=logger)

    @handle_errors()
    async def all_threads(
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取所有连续对话线程"""
        return thread_manager.all_threads(token_claims['user_id'])

    @handle_errors()
    async def new_thread(
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """创建新的连续对话线程"""
        return thread_manager.new_thread(token_claims['user_id'])

    @handle_errors()
    async def load_messages(
        thread_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取连续对话线程的消息"""
        return agent.load_history(token_claims['user_id'], thread_id)

    def _get_models():
        return [m.strip() for m in get_env("ILLUFLY_VALID_MODELS").split(",")]

    @handle_errors()
    async def models(
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取可用的模型列表"""
        return _get_models()

    class ChatRequest(OpenaiRequest):
        """聊天请求"""
        thread_id: str = Field(..., description="线程ID")

    @handle_errors()
    async def chat(
        chat_request: ChatRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """与大模型对话"""
        async def stream_response():
            kwargs = chat_request.model_dump(exclude={"thread_id"})
            logger.info(f"\nchat kwargs >>> {kwargs}")
            model = kwargs.pop("model", _get_models()[0])
            async for chunk in agent.chat(
                user_id=token_claims['user_id'],
                thread_id=chat_request.thread_id,
                model=model,
                **kwargs
            ):
                try:
                    yield f'data: {json.dumps(chunk, ensure_ascii=False)}\n\n'
                except Exception as e:
                    logger.error(f"\nchat response [{model}] >>> {chat_request.model_dump(exclude={'thread_id'})}\n\nerror >>> {e}")

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
