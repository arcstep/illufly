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

from ...envir import get_env
from ...llm import LiteLLM
from ..api_keys import ApiKeysManager
from ..models import HttpMethod, Result, OpenaiRequest, ChatMessage
from ..http import handle_errors

# 创建安全方案
security = HTTPBearer(
    scheme_name="Bearer Auth",
    description="Enter your API key with 'Bearer ' prefix",
    auto_error=True
)

def create_openai_endpoints(
    app: FastAPI,
    api_keys_manager: ApiKeysManager,
    imitator: str = None,
    provider: str = None,
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
    @handle_errors()
    async def chat_completion(chat_request: OpenaiRequest, ak: str = Depends(verify_api_key)):
        llm = LiteLLM(provider=provider, imitator=imitator)
        return await llm.acompletion(**chat_request.model_dump())

    class ModelListResponse(BaseModel):
        object: str = "list"
        data: List[dict]

    @handle_errors()
    async def list_models():
        """列出可用模型
        """
        llm = LiteLLM(provider=provider, imitator=imitator)
        models = await llm.list_models()
        return ModelListResponse(
            data=[m.strip() for m in get_env("ILLUFLY_VALID_MODELS").split(",")]
        )

    return [
        (HttpMethod.POST, f"/chat/completions", chat_completion),
        (HttpMethod.GET,  f"/models", list_models),
    ]
