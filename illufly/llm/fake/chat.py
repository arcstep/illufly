from typing import Union, List, Optional, Dict, Any

from ...io import TextBlock
from ...core.agent import ChatAgent

import time

class FakeLLM(ChatAgent):
    def __init__(self, sleep: float=0, **kwargs):
        super().__init__(threads_group="FAKE_LLM", **kwargs)
        self.threads_group = "fake_llm"
        self.sleep = sleep if sleep > 0 else 0

    def generate(self, messages: List[dict]=None, sleep: float=0, *args, **kwargs):
        # 生成info块
        yield TextBlock("info", f'FakeLLM: {messages}')

        # 调用生成接口
        responses = ["这", "是", "一个", "模拟", "调用", "!"]
        _sleep = self.sleep if sleep <= 0 else sleep
        for content in responses:
            time.sleep(_sleep)
            yield TextBlock("chunk", content)
