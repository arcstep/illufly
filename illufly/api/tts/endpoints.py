from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Tuple

import json
import logging

logger = logging.getLogger(__name__)

from ...tts.service import TTSService

def create_tts_endpoints(app, prefix: str) -> List[Tuple[str, str, callable]]:
    """创建 TTS 相关的路由端点
    
    Args:
        app: FastAPI 应用实例
        prefix: API 前缀
        
    Returns:
        路由处理器列表
    """
    tts_service = TTSService()
    
    async def text_to_speech_stream(texts: List[str]):
        """将文本转换为语音流
        
        Args:
            texts: 要转换的文本列表
            
        Returns:
            SSE 流，每个事件包含一个文本的音频数据
        """
        async def event_generator():
            try:
                async for result in tts_service.text_to_speech(texts):
                    # 将结果转换为 SSE 格式
                    yield f"data: {json.dumps(result)}\n\n"
            except Exception as e:
                logger.error(f"TTS 流处理失败: {str(e)}")
                yield f"data: {json.dumps({'error': str(e), 'status': 'error'})}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
    
    return [
        ("POST", f"{prefix}/tts/stream", text_to_speech_stream)
    ]
