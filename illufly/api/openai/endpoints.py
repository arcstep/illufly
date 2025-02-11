from pydantic import BaseModel
from typing import List, Optional, Union, Dict, Tuple, Callable

from fastapi import FastAPI, HTTPException, Depends, Header, Security
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import json
import time
import asyncio
import uuid
import logging

from datetime import datetime

from ..auth.api_keys import ApiKeysManager
from ..models import HttpMethod, Result

# 模拟的API_KEY
VALID_API_KEY = "sk-1234567890abcdef"

# 创建安全方案
security = HTTPBearer(
    scheme_name="Bearer Auth",
    description="Enter your API key with 'Bearer ' prefix",
    auto_error=True
)

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    """验证 API 密钥
    
    Args:
        credentials: Bearer token 凭证
        
    Returns:
        str: API 密钥
        
    Raises:
        HTTPException: 当 API 密钥无效时抛出
    """
    api_key = credentials.credentials  # 获取 token 部分
    if not api_key.startswith("sk-"):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key format. Expected 'sk-xxx'"
        )
        
    # TODO: 使用 api_keys_manager 验证 API 密钥
    if api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
        
    return api_key

def create_openai_endpoints(
    app: FastAPI,
    api_keys_manager: ApiKeysManager,
    prefix: str = "/api",
    logger: logging.Logger = None
) -> Dict[str, Tuple[HttpMethod, str, Callable]]:
    """创建 OpenAI 接口"""

    class ChatMessage(BaseModel):
        role: str
        content: str

    class ChatRequest(BaseModel):
        model: str
        messages: List[ChatMessage]
        temperature: Optional[float] = None
        top_p: Optional[float] = None
        n: Optional[int] = 1  # 返回的候选数量
        stream: Optional[bool] = False
        stop: Optional[List[str]] = None  # 停止词
        max_tokens: Optional[int] = None
        presence_penalty: Optional[float] = None
        frequency_penalty: Optional[float] = None
        logit_bias: Optional[dict] = None  # logit偏置
        user: Optional[str] = None  # 用户标识
        logprobs: Optional[bool] = None  # 是否返回logprobs
        top_logprobs: Optional[int] = None  # 返回的top logprobs数量
        # 预留未考虑到的参数
        extra: Optional[dict] = None  # 用于兼容未支持的参数

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
        object: str = "chat.completion"
        created: int
        model: str
        choices: List[ChatChoice]
        usage: Optional[UsageInfo] = None  # token使用情况
        system_fingerprint: Optional[str] = None  # 系统指纹
        # 预留未考虑到的参数
        extra: Optional[dict] = None  # 用于兼容未支持的参数

    # 流式响应模型
    class ChatStreamResponse(BaseModel):
        id: str
        object: str = "chat.completion.chunk"
        created: int
        model: str
        choices: List[ChatChoice]

    async def chat_completion(request: ChatRequest, api_key: str = Depends(verify_api_key)):
        response_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_timestamp = int(datetime.now().timestamp())

        if request.stream:
            # 流式响应
            async def generate():
                full_response = "Hello! This is a test response from the OpenAI-compatible API."
                for word in full_response:
                    chunk = word
                    data_dict = {
                        'id': 'chatcmpl-123',
                        'object': 'chat.completion.chunk',
                        'created': created_timestamp,
                        'model': request.model,
                        'choices': [{
                            'index': 0,
                            'delta': {
                                'role': 'assistant',
                                'content': chunk
                            },
                            'finish_reason': None
                        }]
                    }
                    yield f"data: {json.dumps(data_dict)}\n\n"
                    await asyncio.sleep(0.05)  # 模拟延迟
                # 发送结束标志
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")
        else:
            # 普通响应
            return ChatResponse(
                id=response_id,
                created=created_timestamp,
                model=request.model,
                choices=[
                    ChatChoice(
                        index=0,
                        message=ChatMessage(
                            role="assistant",
                            content="Hello! This is a test response from the OpenAI-compatible API."
                        ),
                        finish_reason="stop"
                    )
                ],
                usage=UsageInfo(
                    prompt_tokens=10,
                    completion_tokens=20,
                    total_tokens=30
                ),
                system_fingerprint="fp_9876543210"
            )

    class ModelListResponse(BaseModel):
        data: List[dict]

    async def list_models(api_key: str = Depends(verify_api_key)):
        """列出可用模型
        
        Security:
            - Bearer Authentication
        """
        return ModelListResponse(
            data=[
                {
                    "id": "illufly-v1",
                    "object": "model",
                    "created": 1677652288,
                    "owned_by": "illufly"
                },
                {
                    "id": "gpt-4",
                    "object": "model",
                    "created": 1677652288,
                    "owned_by": "openai"
                }
            ]
        )

    return {
        "chat/completions": (HttpMethod.POST, f"{prefix}/openai/v1/chat/completions", chat_completion),
        "models": (HttpMethod.GET, f"{prefix}/openai/v1/models", list_models),
    }
