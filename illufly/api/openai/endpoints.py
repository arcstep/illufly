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
from ..api_keys import ApiKeysManager
from ..models import HttpMethod, Result
from ...community.models import TextChunk, ToolCallChunk, TextFinal, ToolCallFinal, UsageBlock
from ..http import handle_errors

AGENT = {
    "models": "Agent.models",
    "chat": "Agent.chat",
}

CHAT_DIRECTLY_THREAD_ID = "chat_directly_thread"

# 模拟的API_KEY
VALID_API_KEY = "sk-1234567890abcdef"

# 创建安全方案
security = HTTPBearer(
    scheme_name="Bearer Auth",
    description="Enter your API key with 'Bearer ' prefix",
    auto_error=True
)

async def verify_api_key(
    request: Request,
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
    # 跳过OPTIONS请求的认证
    if request.method == "OPTIONS":
        return

    api_key = credentials.credentials  # 获取 token 部分
    if not api_key.startswith("sk-"):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key format. Expected 'sk-xxx'"
        )
        
    ## 暂时取消校验
    return api_key

    # TODO: 使用 api_keys_manager 验证 API 密钥
    if api_key != VALID_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

def create_openai_endpoints(
    app: FastAPI,
    imitator: str,
    zmq_client: ClientDealer,
    api_keys_manager: ApiKeysManager,
    logger: logging.Logger = None
) -> Dict[str, Tuple[HttpMethod, str, Callable]]:
    """创建 OpenAI 接口"""

    class ChatMessage(BaseModel):
        role: str
        content: str
        tool_calls: Optional[List[dict]] = Field(default=None, description="工具调用")

    class ChatRequest(BaseModel):
        messages: List[ChatMessage] = Field(..., description="消息列表")
        model: str = Field(..., description="模型名称")
        frequency_penalty: Optional[float] = Field(default=0.0, description="频率惩罚")
        max_tokens: Optional[int] = Field(default=None, description="最大token数")
        presence_penalty: Optional[float] = Field(default=0.0, description="存在惩罚")
        response_format: Optional[dict] = Field(default=None, description="响应格式")
        stream: Optional[bool] = Field(default=False, description="是否流式")
        stream_options: Optional[dict] = Field(default=None, description="流式选项")
        temperature: Optional[float] = Field(default=0.0, description="温度")
        top_p: Optional[float] = Field(default=1.0, description="top_p")
        tools: Optional[List[dict]] = Field(default=None, description="工具列表")
        tool_choice: Optional[dict] = Field(default=None, description="工具选择")
        logprobs: Optional[bool] = Field(default=False, description="是否返回logprobs")
        top_logprobs: Optional[int] = Field(default=None, description="返回的top logprobs数量")
        modalities: Optional[List[str]] = Field(default=None, description="模态")
        audio: Optional[dict] = Field(default=None, description="音频")
        seed: Optional[int] = Field(default=None, description="随机种子")
        stop: Optional[List[str]] = Field(default=None, description="停止词")
        n: Optional[int] = Field(default=1, ge=1, le=10, description="返回的候选数量")
        logit_bias: Optional[dict] = Field(default=None, description="logit偏置")
        enable_search: Optional[bool] = Field(default=None, description="是否启用搜索")
        user: Optional[str] = Field(default=None, description="用户标识")
        # 预留未考虑到的参数
        extra: Optional[dict] = Field(default=None, description="用于兼容未支持的参数")

        def model_dump(self, *args, **kwargs):
            kwargs.setdefault('exclude_none', True)
            return super().model_dump(*args, **kwargs)

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

        def model_dump(self, *args, **kwargs):
            kwargs.setdefault('exclude_none', True)
            return super().model_dump(*args, **kwargs)

    # 流式响应模型
    @handle_errors(logger=logger)
    async def chat_completion(chat_request: ChatRequest, api_key: str = Depends(verify_api_key)):
        logger.info(f"chat_request: {chat_request}")
        created_timestamp = int(datetime.now().timestamp())
        if chat_request.stream:
            # 流式响应
            async def generate():
                finish_sent = False
                model = None
                finish_reason = None

                async for chunk in zmq_client.stream(
                    f'{imitator}.chat',
                    user_id=api_key,
                    thread_id=CHAT_DIRECTLY_THREAD_ID,
                    **chat_request.model_dump()
                ):
                    finish_reason = getattr(chunk, 'finish_reason', finish_reason)
                    logger.info(f"block_type: {chunk.block_type}, finish_reason: {finish_reason}")

                    if isinstance(chunk, (TextChunk, ToolCallChunk)):
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
                                    'tool_calls': [t.content for t in chunk.tool_calls] if isinstance(chunk, ToolCallChunk) else None
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
                AGENT["chat"],
                user_id=api_key,
                thread_id=CHAT_DIRECTLY_THREAD_ID,
                **chat_request.model_dump()
            ):
                if isinstance(chunk, (TextFinal, ToolCallFinal)):
                    model = chunk.model
                    response_id = chunk.response_id
                    finish_reason = chunk.finish_reason
                    final_text += chunk.content
                    if isinstance(chunk, ToolCallFinal):
                        final_tool_calls.append(chunk)
                elif isinstance(chunk, UsageBlock):
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
    async def list_models(api_key: str = Depends(verify_api_key)):
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
