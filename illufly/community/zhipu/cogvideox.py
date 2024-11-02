from typing import Union, List, Optional
from urllib.parse import urlparse
import os
import time

from ..http import EventBlock, save_resource, confirm_base64_or_uri
from ...types import BaseAgent
from ...utils import raise_invalid_params
from ...config import get_env

CHECK_RESULT_SECONDS = get_env("HTTP_CHECK_RESULT_SECONDS")

class CogVideoX(BaseAgent):
    """    
    [CogVideoX API](https://open.bigmodel.cn/dev/api/videomodel/cogvideox)
    """
    @classmethod
    def allowed_params(cls):
        return {
            "model": "模型名称",
            "api_key": "API_KEY",
            "base_url": "API_BASE_URL",
            **BaseAgent.allowed_params()
        }

    def __init__(self, model: str=None, **kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())
        try:
            from zhipuai import ZhipuAI
        except ImportError:
            raise ImportError(
                "Could not import zhipuai package. "
                "Please install it via 'pip install -U zhipuai'"
            )

        super().__init__(threads_group="COGVIEW", **kwargs)

        self.default_call_args = {
            "model": model or "cogvideox"
        }
        self.model_args = {
            "api_key": kwargs.get("api_key", os.getenv("ZHIPUAI_API_KEY")),
            "base_url": kwargs.get("base_url", os.getenv("ZHIPUAI_BASE_URL")),
        }
        self.client = ZhipuAI(**self.model_args)

        self.description = "我擅长根据你的文字提示描述生成视频，你必须在 prompt 中详细描述生成要求，你必须展开描述，比如镜头、光线、细部等。"
        self.tool_params = {
            "prompt": "请尽量详细描述生成要求的细节",
            "image_url": "提供基于其生成内容的图像。如果传入此参数，系统将以该图像为基础进行操作。",
            "output": "指定生成视频的名称，应当包括扩展名"
        }

    def call(
        self, 
        prompt: str=None,
        image_url: str=None,
        output: Optional[Union[str, List[str]]] = None,
        **kwargs
    ):
        image_url = confirm_base64_or_uri(image_url)

        _kwargs = self.default_call_args
        _kwargs.update({
            "prompt": prompt,
            "image_url": image_url,
            **kwargs,
        })
        if isinstance(output, str):
            output = [output]

        resp = self.client.videos.generations(**_kwargs)
        while resp.task_status == 'PROCESSING':
            resp = self.client.videos.retrieve_videos_result(id=resp.id)
            yield EventBlock("task_status", f'{resp.id} - {resp.task_status}')

            if resp.task_status == 'SUCCESS':
                for result_index, result in enumerate(resp.video_result):
                    url = result.url
                    cover_url = result.cover_image_url
                    yield EventBlock("video_url", url)
                    if not output or result_index >= len(output):
                        parsed_url = urlparse(url)
                        filename = os.path.basename(parsed_url.path)
                        output_path = f"{filename.rsplit('.', 1)[0]}.{filename.rsplit('.', 1)[1]}"
                    else:
                        output_path = output[result_index]
                    yield from save_resource(url, output_path)
                    yield from save_resource(cover_url, output_path + ".png")

            time.sleep(CHECK_RESULT_SECONDS)
