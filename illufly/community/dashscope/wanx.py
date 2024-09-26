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
    :parameters.style: 输出图像的风格，目前支持以下风格取值：
        - <photography> 摄影,
        - <portrait> 人像写真,
        - <3d cartoon> 3D卡通,
        - <anime> 动画,
        - <oil painting> 油画,
        - <watercolor> 水彩,
        - <sketch> 素描,
        - <chinese painting> 中国画,
        - <flat illustration> 扁平插画,
        - <auto> 默认
    
    :parameters.size: 生成图像的分辨率，目前仅支持：
        - 1024*1024 默认
        - 720*1280
        - 1280*720

    :parameters.ref_mode: 垫图（参考图）生图使用的生成方式，可选值为
        - repaint 参考内容，默认
        - refonly 参考风格

    [详细调用参数可参考通义万相文生图 API](https://help.aliyun.com/zh/dashscope/developer-reference/api-details-9)
    """
    def __init__(self, model: str=None, api_key: str=None, **kwargs):
        super().__init__(threads_group="WANX", **kwargs)
        self.model = model or "wanx-v1"
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")

    def confirm_content_url(self, input: Dict[str, Any], key: str, tail: str="_url") -> str:
        url = input.get(f"{key}{tail}", None)
        if not url:
            file = input.get(key, None)
            url = confirm_upload_file(self.model, file, self.api_key)
        return url

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
            "input": {
                "prompt": input.get("prompt", "")[:500],
                "negative_prompt": input.get("negative_prompt", "")[:500] or None,
                "ref_img": self.confirm_content_url(input, "ref_img", "") or None
            },
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

    :input.model_index: 生成风格。取值范围：
        - 1: 3D卡通形象(3dcartoon)
    """
    def __init__(self, model: str=None, **kwargs):
        super().__init__(model=(model or "wanx-style-cosplay-v1"), **kwargs)

    @property
    def aigc_base_url(self):
        return f"{DASHSCOPE_BASE_URL}/services/aigc/image-generation/generation"

    def get_data(self, input: Dict[str, Any], parameters: Dict[str, Any]=None):
        return {
            "model": self.model,
            "input": {
                "face_image_url": self.confirm_content_url(input, "face_image", "_url"),
                "template_image_url": self.confirm_content_url(input, "template_image", "_url"),
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

class RepaintWanx(CosplayWanx):
    """
    通义万相-人像风格重绘可以将输入的人物图像进行多种风格化的重绘生成，
    使新生成的图像在兼顾原始人物相貌的同时，带来不同风格的绘画效果。
    当前支持预置重绘风格和客户上传风格参考图，
    预置重绘风格有复古漫画、3D童话、二次元、小清新、未来科技、国画古风、将军百战等。

    :input.style_index: 风格索引，取值范围为1-10，默认为-1。
        想要生成的风格化类型索引：
            -1 参考上传图像风格
            0 复古漫画
            1 3D童话
            2 二次元
            3 小清新
            4 未来科技
            5 国画古风
            6 将军百战
            7 炫彩卡通
            8 清雅国风
            9 喜迎新年
    """
    def __init__(self, model: str=None, **kwargs):
        super().__init__(model=(model or "wanx-style-repaint-v1"), **kwargs)

    def get_data(self, input: Dict[str, Any], parameters: Dict[str, Any]=None):
        return {
            "model": self.model,
            "input": {
                "image_url": self.confirm_content_url(input, "image", "_url"),
                "style_ref_url": self.confirm_content_url(input, "style_ref", "_url"),
                "style_index": input.get("style_index", 1)
            }
        }

class BackgroundWanx(Text2ImageWanx):
    """
    通义万相-图像背景生成可以基于输入的前景图像素材拓展生成背景信息，实现自然的光影融合效果，与细腻的写实画面生成。
    """
    def __init__(self, model: str=None, **kwargs):
        super().__init__(model=(model or "wanx-background-generation-v2"), **kwargs)

    @property
    def aigc_base_url(self):
        return f"{DASHSCOPE_BASE_URL}/services/aigc/background-generation/generation/"

    def get_data(self, input: Dict[str, Any], parameters: Dict[str, Any]=None):
        return {
            "model": self.model,
            "input": {
                "base_image_url": self.confirm_content_url(input, "base_image", "_url"),
                "ref_image_url": self.confirm_content_url(input, "ref_image", "_url"),
                "reference_edge": {
                    "foreground_edge": self.confirm_content_url(input, "foregrund", "_edge"),
                    "background_edge": self.confirm_content_url(input, "background", "_edge")
                },
                "neg_ref_prompt": input.get("neg_ref_prompt", "")[:70] or None,
                "ref_prompt": input.get("template_image", "")[:70] or None,
                "title": input.get("title", "")[:8] or None,
                "sub_title": input.get("sub_title", "")[:10] or None
            },
            "parameters": parameters
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

class AnyTextWanx(Text2ImageWanx):
    """
    通义万相-AnyText图文融合，支持图文生成和文字编辑功能，可广泛应用于电商海报、Logo设计、创意涂鸦、表情包、儿童绘本等诸多场景。

    :input.prompt: 半角双引号前需加反斜杠转义字符。
    """
    def __init__(self, model: str=None, **kwargs):
        super().__init__(model=(model or "wanx-anytext-v1"), **kwargs)

    @property
    def aigc_base_url(self):
        return f"{DASHSCOPE_BASE_URL}/services/aigc/anytext/generation/"

    def get_data(self, input: Dict[str, Any], parameters: Dict[str, Any]=None):
        return {
            "model": self.model,
            "input": {
                "mask_image_url": self.confirm_content_url(input, "mask_image", "_url"),
                "base_image_url": self.confirm_content_url(input, "base_image", "_url"),
                "reference_edge": {
                    "foreground_edge": self.confirm_content_url(input, "foregrund", "_edge"),
                    "background_edge": self.confirm_content_url(input, "background", "_edge")
                },
                "prompt": input.get("prompt", None),
                "appended_prompt": input.get("appended_prompt", None),
                "negative_prompt": input.get("negative_prompt", None),
                "layout_priority": input.get("layout_priority", "vertical"),
                "text_position_revise": input.get("text_position_revise", False),
                "title": input.get("title", "")[:8] or None,
                "sub_title": input.get("sub_title", "")[:10] or None
            },
            "parameters": parameters
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

class SketchWanx(Text2ImageWanx):
    """
    通义万相-涂鸦作画通过手绘任意内容加文字描述，即可生成精美的涂鸦绘画作品，
    作品中的内容在参考手绘线条的同时，兼顾创意性和趣味性。
    涂鸦作画支持扁平插画、油画、二次元、3D卡通和水彩5种风格，可用于创意娱乐、辅助设计、儿童教学等场景。

    :parameters.size: 生成图像的分辨率，目前仅支持：
        - 768*768 默认值

    :parameters.style: 输出图像的风格，目前支持以下风格：
        - <3d cartoon> 3D 卡通
        - <anime> 二次元
        - <oil painting> 油画
        - <watercolor> 水彩
        - <flat illustration> 扁平插画
    """
    def __init__(self, model: str=None, **kwargs):
        super().__init__(model=(model or "wanx-sketch-to-image-lite"), **kwargs)

    @property
    def aigc_base_url(self):
        return f"{DASHSCOPE_BASE_URL}/services/aigc/image2image/image-synthesis/"

    def get_data(self, input: Dict[str, Any], parameters: Dict[str, Any]=None):
        return {
            "model": self.model,
            "input": {
                "sketch_image_url": self.confirm_content_url(input, "sketch_image", "_url"),
                "prompt": input.get("prompt", "")[:75],
            },
            "parameters": parameters
        }

class WordArt(Text2ImageWanx):
    """
    WordArt锦书-文字纹理生成可以对输入的文字内容或文字图片进行创意设计，根据提示词内容对文字添加材质和纹理，
    实现立体材质、场景融合、光影特效等效果，生成效果精美、风格多样的艺术字，结合背景可以直接作为文字海报使用。

    input.image 和 input.text 二选一

    :input.image.image_url: 图像要求：
        黑底白字, 图片大小小于5M, 图像格式推荐jpg/png/jpeg/bmp, 长宽比不大于2, 最大边长小于等2048;
        若选择了input.image, 此字段为必须字段

    :input.text.font_name: 当使用input.text时, input.text.ttf_url和input.text.font_name 需要二选一
        - dongfangdakai 阿里妈妈东方大楷, 默认
        - puhuiti_m 阿里巴巴普惠体
        - shuheiti 阿里妈妈数黑体
        - jinbuti 钉钉进步体
        - kuheiti 站酷酷黑体
        - kuaileti 站酷快乐体
        - wenyiti 站酷文艺体
        - logoti 站酷小薇LOGO体
        - cangeryuyangti_m 站酷仓耳渔阳体
        - siyuansongti_b 思源宋体
        - siyuanheiti_m 思源黑体
        - fangzhengkaiti 方正楷体

    :input.text.output_image_ratio: 文字输入的图片的宽高比:
        - 1:1 默认
        - 16:9
        - 9:16

    :parameters.image_short_size: 
    生成的图片短边的长度, 默认为704, 取值范围为[512, 1024],
    若输入数值非64的倍数, 则最终取值为不大于该数值的能被64整除的最大数;
    若输入为图片，输出图片的宽高比和输入图片保持一致.
    """
    def __init__(self, model: str=None, **kwargs):
        super().__init__(model=(model or "wordart-texture"), **kwargs)

    @property
    def aigc_base_url(self):
        return f"{DASHSCOPE_BASE_URL}/services/aigc/wordart/texture"

    def get_data(self, input: Dict[str, Any], parameters: Dict[str, Any]=None):
        image = {
            "image_url": self.confirm_content_url(input, "image", "_url")
        }

        text = {
            "text_content": input.get("text_content", "")[:6] or None,
            "ttf_url": self.confirm_content_url(input, "ttf", "_url"),
            "font_name": input.get("font_name", None),
            "output_image_ratio": input.get("output_image_ratio", '1:1')
        }

        return {
            "model": self.model,
            "input": {
                "image": image if image.get("image_url", None) else None,
                "text": text if text.get("text_content", None) else None,
                "prompt": input.get("prompt")[:200],
                "texture_style": input.get("texture_style", "material")
            },
            "parameters": {
                "n": 1,
                **parameters
            }
        }

class WordArtSemantic(Text2ImageWanx):
    """
    WordArt锦书-文字变形可以对输入的文字边缘轮廓进行创意变形，
    根据提示词内容进行边缘变化，实现一种字体的更多种创意用法，
    返回带有文字内容的黑底白色蒙版图。
    """
    def __init__(self, model: str=None, **kwargs):
        super().__init__(model=(model or "wordart-texture"), **kwargs)

    @property
    def aigc_base_url(self):
        return f"{DASHSCOPE_BASE_URL}/services/aigc/wordart/semantic"

    def get_data(self, input: Dict[str, Any], parameters: Dict[str, Any]=None):
        return {
            "model": self.model,
            "input": {
                "text": input.get("text", None),
                "prompt": input.get("prompt")[:200],
                "texture_style": input.get("texture_style", "material")
            },
            "parameters": {
                "n": 1,
                **parameters
            }
        }
