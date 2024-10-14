from typing import Dict, Any
from .....io import EventBlock, NewLineBlock
from ..base import BaseAgent
from .base import BaseToolCalling
import re
import json

class SingleAction(BaseToolCalling):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def extract_tools_call(self, text: str) -> Dict[str, Any]:
        # 正则表达式解析文本，只提取 Action 后的第一个单词
        pattern = r"Action:\s*(\w+)"
        match = re.search(pattern, text)

        if match:
            action_name = match.group(1).strip()
            arguments = re.search(r"Action Input:\s*(\[.*?\])", text, re.DOTALL).group(1).strip()

            return {
                "function": {
                    "name": action_name,
                    "arguments": arguments
                }
            }
        else:
            return None

    def handle_tools_call(self, text: str):
        action = self.extract_tools_call(text)
        if action:
            for block in self.execute_tool(action):
                yield block

    async def async_handle_tools_call(self, tool_call):
        action = self.extract_tools_call(text)
        if action:
            async for block in self.async_execute_tool(action):
                yield block
