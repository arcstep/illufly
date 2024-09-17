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

from ...io import TextBlock
from ...core.agent import BaseAgent

WANX_SIZE = {
    "720*1280": "720*1280",
    "1024*1024": "1024*1024",
    "768*1152": "768*1152",
    "1280*720": "1280*720",
}

CHECK_RESULT_SECONDS = 2
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
DEFAULT_MODEL = "wanx-sketch-to-image-v1"
COSPLAY_MODEL = "wanx-style-cosplay-v1"
TEXT2IMAGE_MODEL = "wanx-v1"
DEFAULT_FACE_IMAGE_URL = "https://public-vigen-video.oss-cn-shanghai.aliyuncs.com/public/dashscope/test.png"
DEFAULT_TEMPLATE_IMAGE_URL = "https://public-vigen-video.oss-cn-shanghai.aliyuncs.com/public/dashscope/test.png"
DEFAULT_SIZE = "1024*1024"
DEFAULT_REF_MODE = "repaint"

def get_headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-DashScope-Async": "enable"
    }

def validate_output_path(output_path: Union[str, List[str]], n: int) -> List[str]:
    if isinstance(output_path, str):
        output_path = [output_path]
    if output_path and len(output_path) != n:
        raise ValueError(f"Invalid output_path: {output_path}, please ensure the number of images is consistent with the n value")
    return output_path

def save_image(url: str, path: str):
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    with open(path, 'wb+') as f:
        f.write(requests.get(url).content)
        yield TextBlock("info", f'output image to {path}')

async def async_save_image(url: str, path: str):
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            content = await response.read()
            with open(path, 'wb+') as f:
                f.write(content)
                yield TextBlock("info", f'output image to {path}')

class Text2ImageWanx(BaseAgent):
    """
    支持风格包括：水彩、油画、中国画、素描、扁平插画、二次元、3D卡通。

    [详细调用参数可参考通义万相文生图 API](https://help.aliyun.com/zh/dashscope/developer-reference/api-details-9)
    """
    def __init__(self, model: str=None, **kwargs):
        try:
            import dashscope
        except ImportError:
            raise RuntimeError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

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
        response = requests.post(f"{DASHSCOPE_BASE_URL}/services/aigc/text2image/image-synthesis", 
                                 headers=headers, json=data)
        result = response.json()
        yield TextBlock("info", f'{json.dumps(result, ensure_ascii=False)}')
        task_id = result['output']['task_id']
        output_path = validate_output_path(output_path, n)
        
        yield TextBlock("info", f'{task_id}: {result["output"]["task_status"]}')
        if "usage" in result:
            yield TextBlock("usage", json.dumps(result["usage"]))

        while True:
            time.sleep(CHECK_RESULT_SECONDS)
            status_response = requests.get(f"{DASHSCOPE_BASE_URL}/tasks/{task_id}", headers=headers)
            status_result = status_response.json()
            yield TextBlock("info", f'{task_id}: {status_result["output"]["task_status"]}')
            if status_result['output']['task_status'] in ['SUCCEEDED', 'FAILED']:
                break

        if status_result['output']['task_status'] == 'SUCCEEDED':
            results = status_result['output']['results']
            for i, result in enumerate(results):
                url = result['url']
                yield TextBlock("image_url", url)
                if not output_path:
                    parsed_url = urlparse(url)
                    filename = os.path.basename(parsed_url.path)
                    output_path = [f"{filename.rsplit('.', 1)[0]}_{i}.{filename.rsplit('.', 1)[1]}" for i in range(n)]
                for block in save_image(url, output_path[i]):
                    yield block
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
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{DASHSCOPE_BASE_URL}/services/aigc/text2image/image-synthesis", 
                                    headers=headers, json=data) as response:
                result = await response.json()
                yield TextBlock("info", f'{json.dumps(result, ensure_ascii=False)}')
                task_id = result['output']['task_id']
                
                yield TextBlock("info", f'{task_id}: {result["output"]["task_status"]}')
                if "usage" in result:
                    yield TextBlock("usage", json.dumps(result["usage"]))

                while True:
                    await asyncio.sleep(CHECK_RESULT_SECONDS)
                    async with session.get(f"{DASHSCOPE_BASE_URL}/tasks/{task_id}", headers=headers) as status_response:
                        status_result = await status_response.json()
                        yield TextBlock("info", f'{task_id}: {status_result["output"]["task_status"]}')
                        if status_result['output']['task_status'] in ['SUCCEEDED', 'FAILED']:
                            break

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
        try:
            import dashscope
        except ImportError:
            raise RuntimeError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

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

        response = requests.post(f"{DASHSCOPE_BASE_URL}/services/aigc/image-generation/generation", 
                                 headers=headers, json=data)
        result = response.json()
        yield TextBlock("info", f'{json.dumps(result, ensure_ascii=False)}')
        task_id = result['output']['task_id']
        
        yield TextBlock("info", f'{task_id}: {result["output"]["task_status"]}')
        if "usage" in result:
            yield TextBlock("usage", json.dumps(result["usage"]))

        while True:
            time.sleep(CHECK_RESULT_SECONDS)
            status_response = requests.get(f"{DASHSCOPE_BASE_URL}/tasks/{task_id}", headers=headers)
            status_result = status_response.json()
            yield TextBlock("info", f'{task_id}: {status_result["output"]["task_status"]}')
            if status_result['output']['task_status'] in ['SUCCEEDED', 'FAILED']:
                break

        if status_result['output']['task_status'] == 'SUCCEEDED':
            url = status_result['output']['result_url']
            yield TextBlock("image_url", url)

            parsed_url = urlparse(url)
            _output_path = output_path or os.path.basename(parsed_url.path)
            for block in save_image(url, _output_path):
                yield block
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
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{DASHSCOPE_BASE_URL}/services/aigc/image-generation/generation", 
                                    headers=headers, json=data) as response:
                result = await response.json()
                yield TextBlock("info", f'{json.dumps(result, ensure_ascii=False)}')
                task_id = result['output']['task_id']
                
                yield TextBlock("info", f'{task_id}: {result["output"]["task_status"]}')
                if "usage" in result:
                    yield TextBlock("usage", json.dumps(result["usage"]))

                while True:
                    await asyncio.sleep(CHECK_RESULT_SECONDS)
                    async with session.get(f"{DASHSCOPE_BASE_URL}/tasks/{task_id}", headers=headers) as status_response:
                        status_result = await status_response.json()
                        yield TextBlock("info", f'{task_id}: {status_result["output"]["task_status"]}')
                        if status_result['output']['task_status'] in ['SUCCEEDED', 'FAILED']:
                            break

                if status_result['output']['task_status'] == 'SUCCEEDED':
                    url = status_result['output']['result_url']
                    yield TextBlock("image_url", url)

                    parsed_url = urlparse(url)
                    _output_path = output_path or os.path.basename(parsed_url.path)
                    async for block in async_save_image(url, _output_path):
                        yield block
                    if 'usage' in status_result:
                        yield TextBlock("usage", json.dumps(status_result["usage"], ensure_ascii=False))


