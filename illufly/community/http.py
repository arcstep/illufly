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

def send_request(url: str, headers: Dict[str, str], data: Dict[str, Any]) -> Dict[str, Any]:
    response = requests.post(url, headers=headers, json=data)
    return response.json()

async def async_send_request(url: str, headers: Dict[str, str], data: Dict[str, Any]) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as response:
            return await response.json()

def check_task_status(task_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    while True:
        time.sleep(CHECK_RESULT_SECONDS)
        status_response = requests.get(f"{DASHSCOPE_BASE_URL}/tasks/{task_id}", headers=headers)
        status_result = status_response.json()
        # yield TextBlock("info", f'{task_id}: {status_result["output"]["task_status"]}')
        if status_result['output']['task_status'] in ['SUCCEEDED', 'FAILED']:
            return status_result

async def async_check_task_status(task_id: str, headers: Dict[str, str]) -> Dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(CHECK_RESULT_SECONDS)
            async with session.get(f"{DASHSCOPE_BASE_URL}/tasks/{task_id}", headers=headers) as status_response:
                status_result = await status_response.json()
                # yield TextBlock("info", f'{task_id}: {status_result["output"]["task_status"]}')
                if status_result['output']['task_status'] in ['SUCCEEDED', 'FAILED']:
                    return status_result