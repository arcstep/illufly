from typing import List, Dict, Any
from .base import BaseToolCalling
from ......io import EventBlock, NewLineBlock
from ....message import Messages
import json

class ToolCall(BaseToolCalling):

    def extract_tools_call(self, text: str) -> List[Dict[str, Any]]:
        start_marker = "<tool_call>"
        end_marker = "</tool_call>"
        start = text.find(start_marker)
        steps = []
        while start != -1:
            end = text.find(end_marker, start)
            if end != -1:
                tool_call_json = text[start + len(start_marker):end]
                try:
                    tool_call = json.loads(tool_call_json)
                    steps.append({
                        "function": {
                            "name": tool_call.get("name"),
                            "arguments": json.dumps(tool_call.get("arguments", "[]"), ensure_ascii=False)
                        }
                    })
                except json.JSONDecodeError:
                    pass
                start = text.find(start_marker, end)
            else:
                break

        for index, step in enumerate(steps):
            name = step["function"].get("name", "UNKNOWN_FUNCTION")
            arguments = step["function"].get("arguments", "")
            self.steps.append({
                "index": index + 1,
                "eid": f"#E{index + 1}",
                "description": f"调用{name}工具",
                "name": name,
                "arguments": arguments,
                "result": None
            })

        return steps

    def handle(self, steps: List[Any], short_term_memory: Messages, long_term_memory: Messages):
        for index, tool_call in enumerate(steps):
            # 由于工具是从文本中提取的，第一个工具在文本中已经作为AI回复，所以从第二个开始构造记忆
            if index > 0:
                new_task = f'请继续: {json.dumps(tool_call, ensure_ascii=False)}'
                tool_call_message = [
                    {
                        "role": "assistant",
                        "content": new_task
                    }
                ]
                short_term_memory.extend(tool_call_message)
                long_term_memory.extend(tool_call_message)

            # 执行工具
            for block in self.execute_tool(tool_call):
                if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                    tool_resp = block.text
                    tool_resp_message = [
                        {
                            "role": "user",
                            "content": f'<tool_resp>{tool_resp}</tool_resp>'
                        }
                    ]
                    short_term_memory.extend(tool_resp_message)
                    long_term_memory.extend(tool_resp_message)
                    # 补充结果到 steps
                    self.steps[index]["result"] = tool_resp.strip()
                yield block

    async def async_handle(self, steps: List[Any], short_term_memory: Messages, long_term_memory: Messages):
        for index, tool_call in enumerate(steps):
            # 由于工具是从文本中提取的，第一个工具在文本中已经作为AI回复，所以从第二个开始构造记忆
            if index > 0:
                new_task = f'请继续: {json.dumps(tool_call, ensure_ascii=False)}'
                tool_call_message = [
                    {
                        "role": "assistant",
                        "content": new_task
                    }
                ]
                short_term_memory.extend(tool_call_message)
                long_term_memory.extend(tool_call_message)

            # 执行工具
            async for block in self.async_execute_tool(tool_call):
                if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                    tool_resp = block.text
                    tool_resp_message = [
                        {
                            "role": "user",
                            "content": f'<tool_resp>{tool_resp}</tool_resp>'
                        }
                    ]
                    short_term_memory.extend(tool_resp_message)
                    long_term_memory.extend(tool_resp_message)
                    # 补充结果到 steps
                    self.steps[index]["result"] = tool_resp.strip()
                yield block
