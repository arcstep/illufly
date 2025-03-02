from pydantic import BaseModel, Field
from typing import List, Optional, Union, Dict, Tuple, Callable

from fastapi import FastAPI, HTTPException, Depends, Header, Security, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import json
import time
import asyncio
import uuid
import logging

from datetime import datetime

from ...mq import ClientDealer
from ...community.models import BlockType
from ..api_keys import ApiKeysManager
from ..models import HttpMethod, Result, OpenaiRequest, ChatMessage
from ...community.models import TextChunk, ToolCallChunk, TextFinal, ToolCallFinal, UsageBlock
from ..http import handle_errors

CHAT_DIRECTLY_THREAD_ID = "chat_directly_thread"

# 模拟的API_KEY
VALID_API_KEY = "sk-1234567890abcdef"

# 创建安全方案
security = HTTPBearer(
    scheme_name="Bearer Auth",
    description="Enter your API key with 'Bearer ' prefix",
    auto_error=True
)

def create_openai_endpoints(
    app: FastAPI,
    imitator: str,
    zmq_client: ClientDealer,
    api_keys_manager: ApiKeysManager,
    logger: logging.Logger = None
) -> Dict[str, Tuple[HttpMethod, str, Callable]]:
    """创建 OpenAI 接口"""
    # 响应模型
    class UsageInfo(BaseModel):
        prompt_tokens: int
        completion_tokens: int
        total_tokens: int

    class ChatChoice(BaseModel):
        index: int
        message: ChatMessage
        finish_reason: Optional[str] = None
        logprobs: Optional[dict] = None  # 支持logprobs
        delta: Optional[dict] = None  # 用于流式响应

    class ChatResponse(BaseModel):
        id: str
        object: str = Field(default="chat.completion")
        created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
        model: Union[str, None] = Field(default=None)
        choices: List[ChatChoice]
        usage: Optional[UsageInfo] = None  # token使用情况
        system_fingerprint: Optional[str] = None  # 系统指纹
        # 预留未考虑到的参数
        extra: Optional[dict] = None  # 用于兼容未支持的参数

    async def verify_api_key(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Security(security)
    ) -> str:
        """验证 API 密钥"""
        # 跳过OPTIONS请求的认证
        if request.method == "OPTIONS":
            return

        api_key = credentials.credentials  # 获取 token 部分
        if not api_key.startswith("sk-"):
            raise HTTPException(
                status_code=401,
                detail="Invalid API key format. Expected 'sk-xxx'"
            )
            
        res = api_keys_manager.verify_api_key(api_key)
        if res.is_ok() and res.data['imitator'] == imitator:            
            return res.data
        else:
            raise HTTPException(
                status_code=401,
                detail=res.error
            )

    # 流式响应模型
    @handle_errors(logger=logger)
    async def chat_completion(chat_request: OpenaiRequest, ak: str = Depends(verify_api_key)):
        logger.info(f"chat_request: {chat_request.model_dump()}")
        created_timestamp = int(datetime.now().timestamp())
        if chat_request.stream:
            # 流式响应
            async def generate():
                finish_sent = False
                model = None
                finish_reason = None

                async for chunk in zmq_client.stream(
                    f'{imitator}.chat',
                    user_id=ak['user_id'],
                    thread_id=CHAT_DIRECTLY_THREAD_ID,
                    **chat_request.model_dump()
                ):
                    finish_reason = getattr(chunk, 'finish_reason', finish_reason)
                    logger.info(f"block_type: {chunk.block_type}, finish_reason: {finish_reason}")

                    is_text_chunk = getattr(chunk, 'block_type', None) == BlockType.TEXT_CHUNK
                    is_tool_chunk = getattr(chunk, 'block_type', None) == BlockType.TOOL_CALL_CHUNK

                    if is_text_chunk or is_tool_chunk:
                        model = getattr(chunk, 'model', model)
                        data_dict = {
                            'id': chunk.response_id,
                            'object': 'chat.completion.chunk',
                            'created': int(chunk.created_at),
                            'service_tier': None,
                            'system_fingerprint': "fp_123456",
                            'model': model,
                            'choices': [{
                                'index': 0,
                                'delta': {
                                    'role': 'assistant',
                                    'content': chunk.content,
                                    'tool_calls': [t.content for t in chunk.tool_calls] if is_tool_chunk else None
                                },
                                "logprobs": None,
                                'finish_reason': finish_reason
                            }]
                        }
                        if chunk.content or chunk.finish_reason:
                            yield f"data: {json.dumps(data_dict, ensure_ascii=False)}\n\n"
                        
                        # 标记结束状态
                        if chunk.finish_reason:
                            finish_sent = True
                    
                # 确保发送结束标记
                if not finish_sent:
                    yield "data: [DONE]\n\n"
                else:
                    # 部分客户端需要显式结束符
                    yield "data: [DONE]\n\n"

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "X-Accel-Buffering": "no",  # 关键头
                    "Connection": "keep-alive",
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache"
                }
            )

        else:
            final_text = ""
            final_tool_calls = []
            usage = None
            model = chat_request.model
            response_id = None
            finish_reason = None
            async for chunk in zmq_client.stream(
                f'{ak["imitator"]}.chat',
                user_id=ak['user_id'],
                thread_id=CHAT_DIRECTLY_THREAD_ID,
                **chat_request.model_dump()
            ):
                is_text_final = getattr(chunk, 'block_type', None) == BlockType.TEXT_FINAL
                is_tool_final = getattr(chunk, 'block_type', None) == BlockType.TOOL_CALL_FINAL
                is_usage = getattr(chunk, 'block_type', None) == BlockType.USAGE
                if is_text_final or is_tool_final:
                    model = chunk.model
                    response_id = chunk.response_id or str(uuid.uuid4().hex)
                    finish_reason = chunk.finish_reason
                    final_text += chunk.content
                    if is_tool_final:
                        final_tool_calls.append(chunk)
                elif is_usage:
                    usage = chunk

            return ChatResponse(
                id=response_id,
                model=model,
                choices=[
                    ChatChoice(
                        index=0,
                        message=ChatMessage(
                            role="assistant",
                            content=final_text,
                            tool_calls=[t.content for t in final_tool_calls]
                        ),
                        finish_reason=finish_reason
                    )
                ],
                usage=usage.content if usage else None
            )

    class ModelListResponse(BaseModel):
        object: str = "list"
        data: List[dict]

    @handle_errors(logger=logger)
    async def list_models():
        """列出可用模型
        
        Security:
            - Bearer Authentication
        """
        models = await zmq_client.invoke(f'{imitator}.models')
        return ModelListResponse(
            data=models[0]
        )

    return [
        (HttpMethod.POST, f"/chat/completions", chat_completion),
        (HttpMethod.GET,  f"/models", list_models),
    ]
