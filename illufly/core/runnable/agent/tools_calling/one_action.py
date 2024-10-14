from typing import List, Dict, Any
from .....io import EventBlock, NewLineBlock
from ..base import BaseAgent
from .base import BaseToolCalling
import re
import json

class OneAction(BaseToolCalling):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def extract_tools_call(self, text: str) -> Dict[str, Dict[str, Any]]:
        # 正则表达式解析文本
        pattern = r"Plan: (.*?)\n#(E\d+) = (\w+)[\(\[](\{.*?\})[\)\]]"
        self.steps = {}

        for match in re.finditer(pattern, text, re.DOTALL):
            plan_description = match.group(1).strip()
            function_name = match.group(3)
            arguments = match.group(4)  # 保留原始参数字符串，包括占位符

            plan = {
                "description": plan_description,
                "name": function_name,
                "arguments": arguments  # 直接存储原始参数字符串
            }
            self.steps[f"#{match.group(2)}"] = plan

        return self.steps

    def handle_tools_call(self, final_tool_call, kwargs):
        arguments = final_tool_call.get("arguments")

        # 查找并替换占位符
        placeholders = re.findall(r"#E\d+", arguments)
        for placeholder in placeholders:
            if placeholder in self.steps:
                # 假设每个步骤的结果是一个字符串
                result = self.steps[placeholder].get("result", "")
                arguments = arguments.replace(placeholder, json.dumps(result))

        # 将字符串格式的 arguments 转换为字典
        arguments = json.loads(arguments)

        tool_call = {
            "function": {
                "name": final_tool_call.get("name"),
                "arguments": arguments
            }
        }
        for block in self.execute_tool(tool_call, kwargs):
            yield block

    async def async_handle_tools_call(self, final_tool_call, kwargs):
        async for block in self.async_execute_tool(final_tool_call, kwargs):
            yield block
