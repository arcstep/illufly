import json
import os
import asyncio
import aiohttp
import time

from typing import Union, List, Optional, Dict, Any
from http import HTTPStatus
from urllib.parse import urlparse, unquote
from pathlib import PurePosixPath
import requests

from ...types import BaseAgent
from ..http import (
    TextBlock,

    get_headers,
    validate_output_path,

    send_request,
    check_task_status,
    save_image,

    async_send_request,
    async_check_task_status,
    async_save_image
)

from ...config import get_env

DASHSCOPE_BASE_URL = get_env("DASHSCOPE_BASE_URL")

DEFAULT_MODEL = "wanx-sketch-to-image-v1"
COSPLAY_MODEL = "wanx-style-cosplay-v1"
TEXT2IMAGE_MODEL = "wanx-v1"
DEFAULT_FACE_IMAGE_URL = "https://public-vigen-video.oss-cn-shanghai.aliyuncs.com/public/dashscope/test.png"
DEFAULT_TEMPLATE_IMAGE_URL = "https://public-vigen-video.oss-cn-shanghai.aliyuncs.com/public/dashscope/test.png"
DEFAULT_SIZE = "1024*1024"
DEFAULT_REF_MODE = "repaint"


class Text2ImageWanx(BaseAgent):
    """
    支持风格包括：水彩、油画、中国画、素描、扁平插画、二次元、3D卡通。

    [详细调用参数可参考通义万相文生图 API](https://help.aliyun.com/zh/dashscope/developer-reference/api-details-9)
    """
    def __init__(self, model: str=None, **kwargs):
        super().__init__(threads_group="WANX", **kwargs)
        self.default_call_args = {
            "model": model or DEFAULT_MODEL
        }
        self.model_args = {
            "api_key": kwargs.get("api_key", os.getenv("DASHSCOPE_API_KEY"))
        }
    
    def call(self, prompt: str, negative_prompt: Optional[str] = None, ref_img: Optional[str] = None, 
             style: Optional[str] = None, size: Optional[str] = DEFAULT_SIZE, n: int = 1, 
             seed: Optional[int] = None, ref_strength: Optional[float] = None, ref_mode: Optional[str] = DEFAULT_REF_MODE,
             output_path: Optional[Union[str, List[str]]] = None):
        headers = get_headers(self.model_args['api_key'])
        data = {
            "model": TEXT2IMAGE_MODEL,
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "ref_img": ref_img
            },
            "parameters": {
                "style": style,
                "size": size,
                "n": n,
                "seed": seed,
                "ref_strength": ref_strength,
                "ref_mode": ref_mode
            }
        }
        result = send_request(f"{DASHSCOPE_BASE_URL}/services/aigc/text2image/image-synthesis", headers, data)
        yield TextBlock("info", f'{json.dumps(result, ensure_ascii=False)}')
        task_id = result['output']['task_id']
        output_path = validate_output_path(output_path, n)
        
        yield TextBlock("info", f'{task_id}: {result["output"]["task_status"]}')
        if "usage" in result:
            yield TextBlock("usage", json.dumps(result["usage"]))

        status_result = check_task_status(task_id, headers)
        if status_result['output']['task_status'] == 'SUCCEEDED':
            results = status_result['output']['results']
            for i, result in enumerate(results):
                url = result['url']
                yield TextBlock("image_url", url)
                if not output_path:
                    parsed_url = urlparse(url)
                    filename = os.path.basename(parsed_url.path)
                    output_path = [f"{filename.rsplit('.', 1)[0]}_{i}.{filename.rsplit('.', 1)[1]}" for i in range(n)]
                yield from save_image(url, output_path[i])
            if 'usage' in status_result:
                yield TextBlock("usage", json.dumps(status_result["usage"], ensure_ascii=False))

    async def async_call(self, prompt: str, negative_prompt: Optional[str] = None, ref_img: Optional[str] = None, 
                         style: Optional[str] = None, size: Optional[str] = DEFAULT_SIZE, n: int = 1, 
                         seed: Optional[int] = None, ref_strength: Optional[float] = None, ref_mode: Optional[str] = DEFAULT_REF_MODE,
                         output_path: Optional[Union[str, List[str]]] = None):
        headers = get_headers(self.model_args['api_key'])
        data = {
            "model": TEXT2IMAGE_MODEL,
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "ref_img": ref_img
            },
            "parameters": {
                "style": style,
                "size": size,
                "n": n,
                "seed": seed,
                "ref_strength": ref_strength,
                "ref_mode": ref_mode
            }
        }
        output_path = validate_output_path(output_path, n)
        result = await async_send_request(f"{DASHSCOPE_BASE_URL}/services/aigc/text2image/image-synthesis", headers, data)
        yield TextBlock("info", f'{json.dumps(result, ensure_ascii=False)}')
        task_id = result['output']['task_id']
        
        yield TextBlock("info", f'{task_id}: {result["output"]["task_status"]}')
        if "usage" in result:
            yield TextBlock("usage", json.dumps(result["usage"]))

        status_result = await async_check_task_status(task_id, headers)
        if status_result['output']['task_status'] == 'SUCCEEDED':
            results = status_result['output']['results']
            for i, result in enumerate(results):
                url = result['url']
                yield TextBlock("image_url", url)
                if not output_path:
                    parsed_url = urlparse(url)
                    filename = os.path.basename(parsed_url.path)
                    output_path = [f"{filename.rsplit('.', 1)[0]}_{i}.{filename.rsplit('.', 1)[1]}" for i in range(n)]
                async for block in async_save_image(url, output_path[i]):
                    yield block
            if 'usage' in status_result:
                yield TextBlock("usage", json.dumps(status_result["usage"], ensure_ascii=False))

class CosplayWanx(BaseAgent):
    """
    通义万相-Cosplay动漫人物生成通过输入人像图片和卡通形象图片，可快速生成人物卡通写真。目前支持3D卡通形象风格。

    一张人像照片 + 一张卡通风格 = 一张卡通写真

    详细调用参数可参考通义万相 Cosplay API。
    """
    def __init__(self, model: str=None, **kwargs):
        super().__init__(threads_group="WANX", **kwargs)
        self.default_call_args = {
            "model": model or DEFAULT_MODEL
        }
        self.model_args = {
            "api_key": kwargs.get("api_key", os.getenv("DASHSCOPE_API_KEY"))
        }
    
    def call(self, face_image_url: str=None, template_image_url: str=None, model_index: int = 1, 
             output_path: Optional[Union[str, List[str]]] = None):
        headers = get_headers(self.model_args['api_key'])
        data = {
            "model": COSPLAY_MODEL,
            "input": {
                "face_image_url": face_image_url or DEFAULT_FACE_IMAGE_URL,
                "template_image_url": template_image_url or DEFAULT_TEMPLATE_IMAGE_URL,
                "model_index": model_index
            }
        }

        result = send_request(f"{DASHSCOPE_BASE_URL}/services/aigc/image-generation/generation", headers, data)
        yield TextBlock("info", f'{json.dumps(result, ensure_ascii=False)}')
        task_id = result['output']['task_id']
        
        yield TextBlock("info", f'{task_id}: {result["output"]["task_status"]}')
        if "usage" in result:
            yield TextBlock("usage", json.dumps(result["usage"]))

        status_result = check_task_status(task_id, headers)
        if status_result['output']['task_status'] == 'SUCCEEDED':
            url = status_result['output']['result_url']
            yield TextBlock("image_url", url)

            parsed_url = urlparse(url)
            _output_path = output_path or os.path.basename(parsed_url.path)
            yield from save_image(url, _output_path)
            if 'usage' in status_result:
                yield TextBlock("usage", json.dumps(status_result["usage"], ensure_ascii=False))

    async def async_call(self, face_image_url: str=None, template_image_url: str=None, model_index: int = 1, 
                         output_path: Optional[Union[str, List[str]]] = None):
        headers = get_headers(self.model_args['api_key'])
        data = {
            "model": COSPLAY_MODEL,
            "input": {
                "face_image_url": face_image_url or DEFAULT_FACE_IMAGE_URL,
                "template_image_url": template_image_url or DEFAULT_TEMPLATE_IMAGE_URL,
                "model_index": model_index
            }

        }
        result = await async_send_request(f"{DASHSCOPE_BASE_URL}/services/aigc/image-generation/generation", headers, data)
        yield TextBlock("info", f'{json.dumps(result, ensure_ascii=False)}')
        task_id = result['output']['task_id']
        
        yield TextBlock("info", f'{task_id}: {result["output"]["task_status"]}')
        if "usage" in result:
            yield TextBlock("usage", json.dumps(result["usage"]))

        status_result = await async_check_task_status(task_id, headers)
        if status_result['output']['task_status'] == 'SUCCEEDED':
            url = status_result['output']['result_url']
            yield TextBlock("image_url", url)

            parsed_url = urlparse(url)
            _output_path = output_path or os.path.basename(parsed_url.path)
            async for block in async_save_image(url, _output_path):
                yield block
            if 'usage' in status_result:
                yield TextBlock("usage", json.dumps(status_result["usage"], ensure_ascii=False))

