import json
import os

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

class ImageWanx(BaseAgent):
    def __init__(self, model: str=None, **kwargs):
        try:
            import dashscope
        except ImportError:
            raise RuntimeError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

        super().__init__(threads_group="WANX", **kwargs)
        self.default_call_args = {"model": model or dashscope.ImageSynthesis.Models.wanx_v1}
        self.model_args = {
            "api_key": kwargs.get("api_key", os.getenv("DASHSCOPE_API_KEY"))
        }

    def call(
        self,
        prompt: str,
        output_path: str=None,
        **kwargs):
        import dashscope
        dashscope.api_key = self.model_args["api_key"]

        # args = [self.default_call_args.pop("model"), prompt]
        _kwargs = {
            "prompt": prompt,
            "n": 1,
            "size": '1024*1024',
            **self.default_call_args,
            **kwargs
        }

        if _kwargs.get("size") not in WANX_SIZE:
            raise ValueError(f"Invalid size: {_kwargs.get('size')}, please choose from {WANX_SIZE.keys()}")
        if output_path and len(output_path) != _kwargs.get("n"):
            raise ValueError(f"Invalid output_path: {output_path}, please ensure the number of images is consistent with the n value")

        resp = dashscope.ImageSynthesis.call(**_kwargs)
        # print(resp)
        if resp.status_code == HTTPStatus.OK:
            output = resp.output
            # yield TextBlock("usage", rsp.usage)
            # save file to current directory
            if output.task_status in ['SUCCESS', 'SUCCEEDED']:
                used_time = f'timeline: {output.submit_time} -> {output.scheduled_time} -> {output.end_time}'
                usage = f'{json.dumps(resp.usage, ensure_ascii=False)}'
                yield TextBlock("info", used_time)
                yield TextBlock("usage", json.dumps(resp.usage, ensure_ascii=False))
                for index, result in enumerate(output.results):
                    yield TextBlock("image_url", result.url)

                    folder = os.path.dirname(output_path[index])
                    if not os.path.exists(folder):
                        os.makedirs(folder)
                    with open(output_path[index], 'wb+') as f:
                        f.write(requests.get(result.url).content)
                        yield TextBlock("info", f"save image to {output_path[index]}")
            elif output.task_status in ['FAILED']:
                yield TextBlock("warn", ('Failed, code: %s, message: %s' %
                    (output.code, output.message)))
        else:
            yield TextBlock("warn", ('Failed, status_code: %s, code: %s, message: %s' %
                (resp.status_code, resp.code, resp.message)))

