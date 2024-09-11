from typing import Union, List, Optional
from ..base import BaseChat
from ..io import TextBlock
import time


class FakeLLM(BaseChat):
    def __init__(self, sleep_time: float = 0):
        super().__init__()
        self.threads_group = "fake_llm"
        self.sleep_time = sleep_time if sleep_time > 0 else 0

    def generate(self, prompt: Union[str, List[dict]], sleep_time: float = 0):
        # 生成info块
        if isinstance(prompt, str):
            yield TextBlock("info", prompt)
        else:
            for message in prompt:
                yield TextBlock("info", f'{message["role"]}: {message["content"]}')

        # 调用生成接口
        responses = ["这", "是", "一个", "模拟", "调用", "!"]
        _sleep_time = self.sleep_time if sleep_time <= 0 else sleep_time
        for content in responses:
            time.sleep(_sleep_time)
            yield TextBlock("chunk", content)
