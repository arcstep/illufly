from typing import Union, List, Dict, Any
import os
import time
import requests
import aiohttp
import asyncio

from ..io import TextBlock
from ..config import get_env

CHECK_RESULT_SECONDS = get_env("HTTP_CHECK_RESULT_SECONDS")
DASHSCOPE_BASE_URL = get_env("DASHSCOPE_BASE_URL")

def cofirm_upload_file(model: str=None, image_path: str=None, api_key: str=None):
    try:
        from dashscope.utils.oss_utils import upload_file
    except ImportError:
        raise RuntimeError(
            "Could not import dashscope package. "
            "Please install it via 'pip install -U dashscope'"
        )

    if image_path and (image_path.startswith('http://') or image_path.startswith('https://') or image_path.startswith('oss://')):
        return image_path
    if os.path.exists(image_path):
        image = f"file://{os.path.abspath(image_path)}"
        return upload_file(model, image_path, api_key)
    else:
        raise ValueError(f"Invalid image path: {image_path}")


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
        yield TextBlock("info", f'{task_id}: {_status_result["output"]["task_status"]}')

        if _status_result['output']['task_status'] in ['SUCCEEDED', 'FAILED']:
            status_result.update(_status_result)
            break

async def async_check_task_status(status_result: Dict[str, Any], task_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(CHECK_RESULT_SECONDS)
            async with session.get(f"{DASHSCOPE_BASE_URL}/tasks/{task_id}", headers=headers) as status_response:
                _status_result = await status_response.json()
                yield TextBlock("info", f'{task_id}: {_status_result["output"]["task_status"]}')
                if _status_result['output']['task_status'] in ['SUCCEEDED', 'FAILED']:
                    status_result.update(_status_result)
                    break
