from typing import AsyncGenerator, List, Dict, Any
import numpy as np
import soundfile as sf
from pathlib import Path
import torch
from kokoro import KModel, KPipeline
import io
import base64
import json
import logging
from functools import lru_cache
import asyncio
from collections import deque

logger = logging.getLogger(__name__)

class TTSService:
    def __init__(self, cache_size: int = 100, batch_size: int = 1):
        self.repo_id = 'hexgrad/Kokoro-82M-v1.1-zh'
        self.sample_rate = 24000
        self.voice = 'zf_001'
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.batch_size = batch_size
        
        # 初始化模型
        self.model = KModel(repo_id=self.repo_id).to(self.device).eval()
        
        # 初始化英文处理管道
        self.en_pipeline = KPipeline(lang_code='a', repo_id=self.repo_id, model=False)
        
        # 初始化中文处理管道
        self.zh_pipeline = KPipeline(
            lang_code='z', 
            repo_id=self.repo_id, 
            model=self.model, 
            en_callable=self._en_callable
        )
        
        # 初始化处理队列
        self.processing_queue = asyncio.Queue()
        self.result_queue = asyncio.Queue()
        
        # 启动处理任务
        self.processing_task = asyncio.create_task(self._process_queue())
    
    def _en_callable(self, text: str) -> str:
        """处理英文文本"""
        if text == 'Kokoro':
            return 'kˈOkəɹO'
        elif text == 'Sol':
            return 'sˈOl'
        return next(self.en_pipeline(text)).phonemes
    
    def _speed_callable(self, len_ps: int) -> float:
        """根据文本长度调整语速"""
        speed = 0.8
        if len_ps <= 83:
            speed = 1
        elif len_ps < 183:
            speed = 1 - (len_ps - 83) / 500
        return speed * 1.1
    
    @lru_cache(maxsize=100)
    def _generate_speech(self, text: str) -> Dict[str, Any]:
        """生成语音（带缓存）
        
        Args:
            text: 要转换的文本
            
        Returns:
            包含音频数据的字典
        """
        try:
            # 生成语音
            generator = self.zh_pipeline(text, voice=self.voice, speed=self._speed_callable)
            result = next(generator)
            wav = result.audio
            
            # 将音频数据转换为base64
            buffer = io.BytesIO()
            sf.write(buffer, wav, self.sample_rate, format='WAV')
            audio_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            return {
                "text": text,
                "audio": audio_base64,
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"转换文本失败: {text}, 错误: {str(e)}")
            return {
                "text": text,
                "error": str(e),
                "status": "error"
            }
    
    async def _process_queue(self):
        """处理队列中的文本"""
        while True:
            try:
                # 获取一批文本
                batch = []
                for _ in range(self.batch_size):
                    try:
                        item = await asyncio.wait_for(self.processing_queue.get(), timeout=0.1)
                        batch.append(item)
                    except asyncio.TimeoutError:
                        break
                
                if not batch:
                    await asyncio.sleep(0.1)
                    continue
                
                # 处理这批文本
                for index, text in batch:
                    result = self._generate_speech(text)
                    result["index"] = index
                    await self.result_queue.put(result)
                
            except Exception as e:
                logger.error(f"处理队列失败: {str(e)}")
                await asyncio.sleep(0.1)
    
    async def text_to_speech(self, texts: List[str]) -> AsyncGenerator[Dict[str, Any], None]:
        """将文本转换为语音，并生成音频数据
        
        Args:
            texts: 要转换的文本列表
            
        Yields:
            包含音频数据的字典，格式为：
            {
                "text": "原始文本",
                "audio": "base64编码的音频数据",
                "index": 当前文本的索引
            }
        """
        # 将文本添加到处理队列
        for i, text in enumerate(texts):
            await self.processing_queue.put((i, text))
        
        # 从结果队列获取结果
        for _ in range(len(texts)):
            result = await self.result_queue.get()
            yield result 