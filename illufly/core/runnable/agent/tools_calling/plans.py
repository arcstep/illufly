from typing import List, Dict, Any
from .....io import EventBlock, NewLineBlock
from ..base import BaseAgent
from .base import BaseToolCalling
import re
import json

class Plans(BaseToolCalling):
    def __init__(self, steps: Dict[str, Dict[str, Any]] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.steps = steps or {}

    def extract_tools_call(self, text: str) -> Dict[str, Dict[str, Any]]:
        # 正则表达式解析文本
        # Regex to match expressions of the form Plan: ... #E... = ...[{"p1":"v1","p2":"v2"}]
        pattern = r"Plan:\s*(.+?)\s*#(E\d+)\s*=\s*(\w+)[\(\[](\{.*?\})[\)\]]"
        self.steps = []

        for match in re.finditer(pattern, text, re.DOTALL):
            plan_description = match.group(1).strip()
            function_name = match.group(3)
            arguments = match.group(4)  # 保留原始参数字符串，包括占位符

            plan = {
                "id": f"#{match.group(2)}",
                "description": plan_description,
                "name": function_name,
                "arguments": arguments  # 直接存储原始参数字符串
            }
            self.steps.append(plan)

        return self.steps

    def handle(self, text: str):
        """
        处理单个计划的调用。
        """
        pre_build_vars = {}

        for plan in self.extract_tools_call(text):
            arguments = plan.get("arguments", "{}")

            # 查找并替换占位符
            placeholders = re.findall(r"#E\d+", arguments)
            for placeholder in placeholders:
                if placeholder in pre_build_vars:
                    # 假设每个步骤的结果是一个字符串
                    result = pre_build_vars[placeholder]
                    if result:
                        # 使用转义的双引号包围替换的结果
                        arguments = arguments.replace(f'"{placeholder}"', json.dumps(result, ensure_ascii=False))

            # 确保 arguments 是有效的 JSON
            try:
                parsed_arguments = json.loads(arguments)
                arguments = json.dumps(parsed_arguments, ensure_ascii=False)
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError: {e}")
                continue

            tool_to_exec = {
                "function": {
                    "name": plan.get("name"),
                    "arguments": arguments
                }
            }
            for block in self.execute_tool(tool_to_exec):
                if block.block_type == "tool_resp_final":
                    # 将结果存储到 pre_build_vars 中
                    pre_build_vars[plan["id"]] = block.text
                yield block

    async def async_handle(self, final_tool_call):
        async for block in self.async_execute_tool(final_tool_call):
            yield block

    @property
    def tools_desc(self) -> str:
        """
        将工具描述转换为 Plan 模式。
        """
        desc = []
        for index, t in enumerate(self.tools_to_exec):
            tool_desc = []
            for k, v in t.parameters["properties"].items():
                tool_desc.append(f"{k}的类型为{v['type']},(目的是){v['description']}")
            desc.append(f'({index+1}){t.name}[{",".join([p for p in t.parameters["properties"]])}]: {t.description}。 {";".join(tool_desc)}')
        return "\n".join(desc)
