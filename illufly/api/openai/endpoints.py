from pydantic import BaseModel
from typing import List, Optional, Union

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

import json
import time
import asyncio
import uuid
from datetime import datetime

app = FastAPI()

# 添加 CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头
)

# 模拟的API_KEY
VALID_API_KEY = "sk-1234567890abcdef"

# 请求模型
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

# API_KEY验证
async def verify_api_key(api_key: str = Header(..., alias="Authorization")):
    if api_key != f"Bearer {VALID_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key

# 对话接口
@app.post("/v1/chat/completions")
async def chat_completion(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    response_id = f"chatcmpl-{uuid.uuid4().hex}"
    created_timestamp = int(datetime.now().timestamp())

    if request.stream:
        # 流式响应
        async def generate():
            full_response = "Hello! This is a test response from the OpenAI-compatible API."
            for i in range(len(full_response)):
                chunk = full_response[:i+1]
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

@app.get("/v1/models", response_model=ModelListResponse)
async def list_models(api_key: str = Depends(verify_api_key)):
    return {
        "data": [
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
    }
