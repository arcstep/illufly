from typing import Union, List, Optional, Dict, Any, Callable

from .....io import EventBlock, NewLineBlock
from .....utils import count_tokens
from .base import ChatAgent

import os
import json

class ChatPool(ChatAgent):
    def __init__(self, *agents, **kwargs):
        self.agents_pool = {a.name: a for a in list(agents)}
        super().__init__(threads_group="CHAT_POOL", **kwargs)

    def get_input_tokens(self, messages: List[dict]):
        msg_len = count_tokens(json.dumps(messages, ensure_ascii=False))
        msg_len += count_tokens(json.dumps(kwargs.get("tools", []), ensure_ascii=False))
        return msg_len

    def generate(
        self,
        messages: List[dict],
        select: Union[str, Callable]=None,
        **kwargs
    ):
        if callable(select):
            _select = select(self.agents_pool)
        else:
            _select = select

        selected_agent = self.agents_pool.get(_select or list(self.agents_pool.keys())[0], None)
        if not selected_agent:
            raise ValueError(f"Agent not found in pool by {select}")

        yield from selected_agent.generate(messages, **kwargs)

