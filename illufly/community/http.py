from typing import Union, List, Dict, Any
import os
import time
import requests
import aiohttp
import asyncio
import hashlib
import base64

from ..io import EventBlock
from ..config import get_env

CHECK_RESULT_SECONDS = get_env("HTTP_CHECK_RESULT_SECONDS")
DASHSCOPE_BASE_URL = get_env("DASHSCOPE_BASE_URL")
ZHIPUAI_API_TOOLS_BASE_URL = get_env("ZHIPUAI_API_TOOLS_BASE_URL")

# 保留当日上传过的缓存
# 缓存的命名：以年月作为子目录，将上传内容和日期一起做MD5编码作为文件名称

def get_upload_cache(file_path: str, upload_server: str="aliyun_oss") -> str:
    UPLOAD_CACHE_DIR = get_env("ILLUFLY_UPLOAD_CACHE")
    date_dir = time.strftime("%Y-%m")
    cache_dir = os.path.join(UPLOAD_CACHE_DIR, date_dir, upload_server)
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            file_content = f.read()
            content_md5 = hashlib.md5(file_content).hexdigest() + ".json"
            cache_path = os.path.join(cache_dir, content_md5)
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    return {"upload_url": f.read(), "cache_path": cache_path}
            else:
                return {"upload_url": None, "cache_path": cache_path}
    return {"upload_url": None, "cache_path": None}

def update_upload_cache(file_path: str, upload_url: str, upload_server: str="aliyun_oss") -> dict:
    cache = get_upload_cache(file_path, upload_server)
    cache_file_path = cache['cache_path']

    if cache_file_path and upload_url:
        os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
        with open(cache_file_path, 'w') as f:
            f.write(upload_url)
            return {"upload_url": upload_url, "cache_path": cache_file_path}

    return {"upload_url": None, "cache_path": cache_file_path}

def confirm_upload_file(model: str=None, uri: str=None, api_key: str=None):
    try:
        from dashscope.utils.oss_utils import upload_file
    except ImportError:
        raise RuntimeError(
            "Could not import dashscope package. "
            "Please install it via 'pip install -U dashscope'"
        )

    if uri and (uri.startswith('http://') or uri.startswith('https://') or uri.startswith('oss://')):
        return uri
    
    media_file_path = os.path.join(get_env("ILLUFLY_RESOURCE"), uri)
    if os.path.exists(media_file_path):
        cache = get_upload_cache(media_file_path, "aliyun_oss")
        if cache['cache_path'] and cache['upload_url']:
            return cache['upload_url']
        else:
            oss_file = f"file://{media_file_path}"
            upload_url = upload_file(model, oss_file, api_key)
            update_upload_cache(media_file_path, upload_url, "aliyun_oss")
            return upload_url
    else:
        raise ValueError(f"Invalid URI path: {uri}")

def confirm_base64_or_uri(uri: str) -> str:
    if uri:
        if uri.startswith('http://') or uri.startswith('https://') or uri.startswith('oss://'):
            return uri
        else:
            with open(uri, 'rb') as file:
                base64_encoded = base64.b64encode(file.read()).decode('utf-8')
                return base64_encoded
    else:
        return uri

def get_headers(api_key: str, enable_async: bool = True) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-DashScope-OssResourceResolve": "enable"
    }
    if enable_async:
        headers["X-DashScope-Async"] = "enable"
    return headers

def validate_output_path(output_path: Union[str, List[str]], n: int) -> List[str]:
    if isinstance(output_path, str):
        output_path = [output_path]
    if output_path and len(output_path) != n:
        raise ValueError(f"Invalid output_path: {output_path}, please ensure the number of images is consistent with the n value")
    return output_path

def save_resource(url: str, path: str):
    res_to_save = os.path.join(get_env("ILLUFLY_RESOURCE"), path)
    if res_to_save and not os.path.exists(res_to_save):
        os.makedirs(os.path.dirname(res_to_save), exist_ok=True)
    with open(res_to_save, 'wb+') as f:
        f.write(requests.get(url).content)
        yield EventBlock("chunk", f'resource was generated and saved to {path}; ')

async def async_save_resource(url: str, path: str):
    res_to_save = os.path.join(get_env("ILLUFLY_RESOURCE"), path)
    if res_to_save and not os.path.exists(res_to_save):
        os.makedirs(os.path.dirname(res_to_save), exist_ok=True)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            content = await response.read()
            with open(res_to_save, 'wb+') as f:
                f.write(content)
                yield EventBlock("chunk", f'an resource was generated and saved to {path}')

def get_request(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    response = requests.get(url, headers=headers)
    return response.json()

async def async_get_request(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            return await response.json()

def send_request(url: str, headers: Dict[str, str], data: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(url, headers=headers, json=data)
    return response.json()

async def async_send_request(url: str, headers: Dict[str, str], data: Dict[str, Any]) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            return await response.json()

def check_task_status(status_result: Dict[str, Any], task_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    while True:
        time.sleep(CHECK_RESULT_SECONDS)
        status_response = requests.get(f"{DASHSCOPE_BASE_URL}/tasks/{task_id}", headers=headers)
        _status_result = status_response.json()
        yield EventBlock("info", f'{task_id}: {_status_result["output"]["task_status"]}')

        if _status_result['output']['task_status'] in ['SUCCEEDED', 'FAILED']:
            status_result.update(_status_result)
            break

async def async_check_task_status(status_result: Dict[str, Any], task_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(CHECK_RESULT_SECONDS)
            async with session.get(f"{DASHSCOPE_BASE_URL}/tasks/{task_id}", headers=headers) as status_response:
                _status_result = await status_response.json()
                yield EventBlock("info", f'{task_id}: {_status_result["output"]["task_status"]}')
                if _status_result['output']['task_status'] in ['SUCCEEDED', 'FAILED']:
                    status_result.update(_status_result)
                    break


