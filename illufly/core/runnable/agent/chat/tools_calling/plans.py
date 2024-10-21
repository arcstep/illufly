from typing import List, Dict, Any
from ......io import EventBlock, NewLineBlock
from ....message import Messages
from ...base import BaseAgent
from .base import BaseToolCalling
import re
import json

class Plans(BaseToolCalling):
    def __init__(self, steps: Dict[str, Dict[str, Any]] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def completed_work(self):
        """
        返回所有步骤的完成情况。
        """
        completed_work = []
        for step in self.steps:
            desc = f'Step{step.get("index", 0)}: {step.get("description", "No description")}'
            e = f'{step.get("eid", "#E0")} = {step.get("name", "")}[{step.get("arguments", "")}]'
            result = step.get("result", None)
            if result:
                result = f'{step.get("name", "")} Value = {result}'
            completed_work.append(f'{desc} \n{e} \n{result or ""}')
        return "\n".join(completed_work)

    def extract_tools_call(self, text: str) -> Dict[str, Dict[str, Any]]:
        # 正则表达式解析文本
        # Regex to match expressions of the form Step1: ... #E... = ...[{"p1":"v1","p2":"v2"}]
        pattern_full = r"Step(\d+):\s*(.+?)\s*#(E\d+)\s*=\s*(\w+)(?:[\(\[](\{.*?\})[\)\]])?"
        pattern_partial = r"Step(\d+):\s*(.*)(#E\d+)\s*"
        steps = []
        
        for line in text.splitlines():
            if not line:
                continue

            match_full = re.search(pattern_full, line)
            
            if match_full:
                index = match_full.group(1).strip()
                description = match_full.group(2).strip()
                eid = match_full.group(3).strip()
                function_name = match_full.group(4).strip()
                arguments = match_full.group(5).strip() if match_full.group(5) else ""
                
                # 确保 match_full 的关键字段不为空
                if eid and function_name:
                    step = {
                        "index": f"{index}",
                        "eid": eid,
                        "description": description,
                        "name": function_name,
                        "arguments": arguments,
                        "result": ""
                    }
                    steps.append(step)
                    continue

            # 如果 match_full 不成功或关键字段为空，尝试 match_partial
            match_partial = re.search(pattern_partial, line)
            if match_partial:
                index = match_partial.group(1).strip()
                eid = f'#E{index}'
                description = match_partial.group(2).strip() + f" {eid}"
                function_name = ""
                arguments = ""
            else:
                continue

            step = {
                "index": f"{index}",
                "eid": eid,
                "description": description,
                "name": function_name,
                "arguments": arguments,
                "result": None
            }
            steps.append(step)

        self.steps.extend(steps)
        return steps

    def handle(self, steps: List[Any], **kwargs):
        """
        处理单个计划的调用。
        """
        pre_build_vars = {}

        for step in steps:
            arguments = step.get("arguments", "")
            # 查找并替换占位符
            placeholders = re.findall(r"#E\d+", arguments)
            for placeholder in placeholders:
                if placeholder in pre_build_vars:
                    # 假设每个步骤的结果是一个字符串
                    result = pre_build_vars[placeholder]
                    if result:
                        # 情况2: "#E{n}" 的结构，有双引号包围
                        if re.fullmatch(rf'"{placeholder}"', arguments):
                            arguments = arguments.replace(f'"{placeholder}"', f'"{result}"')
                        # 情况3: "otherword#E{n}otherword" 的字结构，有双引号包围
                        elif re.search(rf'"[^"]*{placeholder}[^"]*"', arguments):
                            arguments = arguments.replace(placeholder, result)
                        # 情况4: #E{n}，但没有双引号包围
                        elif re.fullmatch(rf'{placeholder}', arguments):
                            arguments = arguments.replace(placeholder, json.dumps(result, ensure_ascii=False))

            # 确保 arguments 是有效的 JSON
            if arguments:  # 仅在 arguments 非空时尝试解析
                try:
                    parsed_arguments = json.loads(arguments)
                    arguments = json.dumps(parsed_arguments, ensure_ascii=False)

                    tool_to_exec = {
                        "function": {
                            "name": step.get("name"),
                            "arguments": arguments
                        }
                    }
                    for block in self.execute_tool(tool_to_exec):
                        if block.block_type == "final_tool_resp":
                            # 将结果存储到 pre_build_vars 中
                            pre_build_vars[step["eid"]] = block.text
                            step["result"] = block.text.strip()
                        yield block

                except json.JSONDecodeError as e:
                    print(f"JSONDecodeError: {e} in arguments: {arguments}")

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
