from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import logging

logger = logging.getLogger("illufly.tts")

# 创建一个简单的路由器
router = APIRouter(tags=["Illufly Backend - TTS"])

# 全局TTS配置
TTS_HOST = None
TTS_PORT = None

async def proxy_request(request: Request, path: str):
    """简单的代理转发函数"""
    if not TTS_HOST or not TTS_PORT:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "error": "TTS服务未配置"}
        )
    
    target_url = f"http://{TTS_HOST}:{TTS_PORT}{path}"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # 读取原始请求内容
            body = await request.body()
            
            # 转发请求
            response = await client.request(
                method=request.method,
                url=target_url,
                params=dict(request.query_params),
                headers={k: v for k, v in request.headers.items() 
                         if k.lower() not in ("host", "content-length")},
                content=body,
                cookies=request.cookies
            )
            
            # 返回响应
            return StreamingResponse(
                content=response.aiter_bytes(),
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type", "application/json")
            )
            
        except Exception as e:
            logger.error(f"TTS代理错误: {e}")
            return JSONResponse(
                status_code=503,
                content={"status": "error", "error": str(e)}
            )

# 明确定义三个主要路由
@router.post("/api/tts")
async def text_to_speech(request: Request):
    """将文本转换为语音
    
    发送文本内容，返回对应的音频数据
    """
    return await proxy_request(request, "/api/tts")

@router.get("/api/tts/voices")
async def get_voices(request: Request):
    """获取可用语音列表
    
    返回所有可用的TTS语音列表
    """
    return await proxy_request(request, "/api/tts/voices")

@router.get("/api/tts/info")
async def get_info(request: Request):
    """获取TTS服务信息
    
    返回TTS服务的配置和状态信息
    """
    return await proxy_request(request, "/api/tts/info")

# 简单的初始化函数
def setup_tts_proxy(app, host=None, port=None):
    """设置TTS代理"""
    global TTS_HOST, TTS_PORT
    
    TTS_HOST = host
    TTS_PORT = port
    
    # 注册路由
    app.include_router(router)
    
    return bool(host and port)