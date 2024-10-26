from typing import Union, List

from ...utils import raise_invalid_params, filter_kwargs
from ...io import EventBlock, NewLineBlock
from ...core.runnable.agent import ChatAgent
from ...core.runnable.message import Messages
import time

class FakeLLM(ChatAgent):
    @classmethod
    def allowed_params(cls):
        return {
            "response": "响应内容",
            "sleep": "睡眠时间",
            **ChatAgent.allowed_params(),
        }

    def __init__(self, response: Union[str, List[str]]=None, sleep: float=None, **kwargs):
        raise_invalid_params(kwargs, self.allowed_params())
        super().__init__(threads_group="FAKE_LLM", **filter_kwargs(kwargs, self.allowed_params()))

        self.sleep = sleep if sleep is not None else 0.01
        self.response = response if isinstance(response, list) else ([response] if response else None)
        self.current_response_index = 0

    def generate(self, prompt: Union[str, List[str]], sleep: float=0, **kwargs):
        yield EventBlock("info", f'I am FakeLLM')

        _sleep = self.sleep if sleep <= 0 else sleep

        if self.response:
            resp = self.response[self.current_response_index]
            self.current_response_index = (self.current_response_index + 1) % len(self.response)
        else:
            std_msg = Messages(prompt, style="text")
            resp = f"Reply >> {std_msg.last_content}"

        for content in resp:
            time.sleep(_sleep)
            yield EventBlock("chunk", content)
        yield NewLineBlock()
