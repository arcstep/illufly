from typing import Union, List, Optional
from urllib.parse import urlparse
import os

from ..http import EventBlock, save_resource
from ...types import BaseAgent
from ...utils import raise_invalid_params

class CogView(BaseAgent):
    """    
    [CogView API](https://open.bigmodel.cn/dev/api/image-model/cogview)
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
            "model": model or "cogview-3-plus"
        }
        self.model_args = {
            "api_key": kwargs.get("api_key", os.getenv("ZHIPUAI_API_KEY")),
            "base_url": kwargs.get("base_url", os.getenv("ZHIPUAI_BASE_URL")),
        }
        self.client = ZhipuAI(**self.model_args)

        self.description = "我擅长根据你的文字提示描述生成图片，你必须在 prompt 中详细描述生成要求，你必须展开描述，比如镜头、光线、细部等。"
        self.tool_params = {
            "prompt": "请尽量详细描述生成要求的细节",
            "size": "图片尺寸, 可选范围: [1024x1024,768x1344,864x1152,1344x768,1152x864,1440x720,720x1440]，默认是1024x1024。",
            "output": "指定生成图片的名称，应当包括扩展名"
        }

    def call(
        self, 
        prompt: str=None,
        size: str=None,
        output: Optional[Union[str, List[str]]] = None,
        **kwargs
    ):
        _kwargs = self.default_call_args
        _kwargs.update({
            "prompt": prompt,
            "size": size or "1024x1024",
            **kwargs,
        })
        if isinstance(output, str):
            output = [output]

        resp = self.client.images.generations(**_kwargs)
        for result_index, result in enumerate(resp.data):
            url = result.url
            yield EventBlock("image_url", url)
            if not output or result_index >= len(output):
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path)
                output_path = f"{filename.rsplit('.', 1)[0]}.{filename.rsplit('.', 1)[1]}"
            else:
                output_path = output[result_index]
            yield from save_resource(url, output_path)
