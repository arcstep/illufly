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
    async_save_image,

    DASHSCOPE_BASE_URL,
    confirm_upload_file
)

class Text2ImageWanx(BaseAgent):
    """
    支持风格包括：水彩、油画、中国画、素描、扁平插画、二次元、3D卡通。
    [详细调用参数可参考通义万相文生图 API](https://help.aliyun.com/zh/dashscope/developer-reference/api-details-9)
    """
    def __init__(self, model: str=None, api_key: str=None, **kwargs):
        super().__init__(threads_group="WANX", **kwargs)
        self.model = model or "wanx-v1"
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
    
    def get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-DashScope-OssResourceResolve": "enable",
            "X-DashScope-Async": "enable"
        }

    def get_data(self, input: Dict[str, Any], parameters: Dict[str, Any]=None):
        ref_img = input.get("ref_img", None)
        ref_img_url = confirm_upload_file(self.model, ref_img, self.api_key) if ref_img else None
        input.update({"ref_img": ref_img_url})
        return {
            "model": self.model,
            "input": input,
            "parameters": parameters or {}
        }
    
    def parse_result(self, status_result, output):
        n = len(output or [])
        if status_result['output']['task_status'] == 'SUCCEEDED':
            results = status_result['output']['results']
            for result_index, result in enumerate(results):
                url = result['url']
                yield TextBlock("image_url", url)
                if not output or result_index >= len(output):
                    parsed_url = urlparse(url)
                    filename = os.path.basename(parsed_url.path)
                    output_path = f"{filename.rsplit('.', 1)[0]}.{filename.rsplit('.', 1)[1]}"
                else:
                    output_path = output[result_index]
                yield from save_image(url, output_path)
            if 'usage' in status_result:
                yield TextBlock("usage", json.dumps(status_result["usage"], ensure_ascii=False))

    def parse_resp(self, resp):
        yield TextBlock("info", f'{json.dumps(resp, ensure_ascii=False)}')
        # 解析提交结果
        task_id = resp['output']['task_id']        
        yield TextBlock("info", f'{task_id}: {resp["output"]["task_status"]}')
        if "usage" in resp:
            yield TextBlock("usage", json.dumps(resp["usage"]))
    
    @property
    def aigc_base_url(self):
        return f"{DASHSCOPE_BASE_URL}/services/aigc/text2image/image-synthesis"
    
    def call(
        self, 
        input: Dict[str, Any],
        parameters: Optional[Dict[str, Any]]=None,
        output: Optional[Union[str, List[str]]] = None,
        **kwargs
    ):
        parameters = parameters or {}
        if isinstance(output, str):
            output = [output]

        # 异步提交生成请求
        headers = self.get_headers()
        data = self.get_data(input, parameters)
        resp = send_request(self.aigc_base_url, headers, data)

        # 解析异步提交响应
        yield from self.parse_resp(resp)

        # 等待异步生成结果
        status_result = {}
        yield from check_task_status(status_result, resp['output']['task_id'], headers)
        yield from self.parse_result(status_result, output)

    async def async_call(
        self, 
        input: Dict[str, Any]=None,
        parameters: Optional[Dict[str, Any]]=None,
        output: Optional[Union[str, List[str]]] = None,
        **kwargs
    ):
        if isinstance(output, str):
            output = [output]

        # 异步提交生成请求
        headers = self.get_headers()
        data = self.get_data(input, parameters)
        resp = await async_send_request(self.aigc_base_url, headers, data)

        # 解析异步提交响应
        for block in self.parse_resp(resp):
            yield block

        # 等待生成结果
        status_result = {}
        async for block in async_check_task_status(status_result, resp['output']['task_id'], headers):
            yield block
        for block in self.parse_result(status_result, output):
            yield block

class CosplayWanx(Text2ImageWanx):
    """
    通义万相-Cosplay动漫人物生成通过输入人像图片和卡通形象图片，可快速生成人物卡通写真。目前支持3D卡通形象风格。
    一张人像照片 + 一张卡通风格 = 一张卡通写真
    详细调用参数可参考通义万相 Cosplay API。
    """
    def __init__(self, model: str=None, **kwargs):
        super().__init__(model=(model or "wanx-style-cosplay-v1"), **kwargs)

    @property
    def aigc_base_url(self):
        return f"{DASHSCOPE_BASE_URL}/services/aigc/image-generation/generation"

    def get_data(self, input: Dict[str, Any], parameters: Dict[str, Any]=None):
        face_image = input.get("face_image_url", None)
        if not face_image:
            file = input.get("face_image", None)
            face_image = confirm_upload_file(self.model, file, self.api_key)
        template_image = input.get("template_image_url", None)
        if not template_image:
            file = input.get("template_image", None)
            template_image = confirm_upload_file(self.model, file, self.api_key)
        return {
            "model": self.model,
            "input": {
                "face_image_url": face_image,
                "template_image_url": template_image,
                "model_index": input.get("model_index", 1)
            }
        }

    def parse_result(self, status_result, output):
        n = len(output or [])
        if status_result['output']['task_status'] == 'SUCCEEDED':
            url = status_result['output']['result_url']
            yield TextBlock("image_url", url)
            if not output:
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path)
                output_path = f"{filename.rsplit('.', 1)[0]}.{filename.rsplit('.', 1)[1]}"
            else:
                output_path = output[0]
            yield from save_image(url, output_path)
            if 'usage' in status_result:
                yield TextBlock("usage", json.dumps(status_result["usage"], ensure_ascii=False))
