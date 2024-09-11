import time

from typing import Union, List, Optional, Dict, Any
from .agent import ChatAgent
from ..io import TextBlock


class FakeLLM(ChatAgent):
    def __init__(self, sleep_time: float=0, **kwargs):
        super().__init__(threads_group="FAKE_LLM", **kwargs)
        self.threads_group = "fake_llm"
        self.sleep_time = sleep_time if sleep_time > 0 else 0

    def generate(self, messages: List[dict], sleep_time: float=0, *args, **kwargs):
        # 生成info块
        for message in messages:
            yield TextBlock("info", f'{message["role"]}: {message["content"]}')

        # 调用生成接口
        responses = ["这", "是", "一个", "模拟", "调用", "!"]
        _sleep_time = self.sleep_time if sleep_time <= 0 else sleep_time
        for content in responses:
            time.sleep(_sleep_time)
            yield TextBlock("chunk", content)
