from typing import List, Dict, Any
from .base import BaseToolCalling
from ......io import EventBlock, NewLineBlock
import json

class SubTask(BaseToolCalling):

    def extract_tools_call(self, text: str) -> List[Dict[str, Any]]:
        start_marker = "<sub_task>"
        end_marker = "</sub_task>"
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

    def handle(self, steps: List[Any], **kwargs):
        for index, tool_call in enumerate(steps):
            for block in self.execute_tool(tool_call):
                if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                    self.steps[index]["result"] = block.text.strip()
                yield block

    async def async_handle(self, steps: List[Any], **kwargs):
        for index, tool_call in enumerate(steps):
            async for block in self.async_execute_tool(tool_call):
                if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                    self.steps[index]["result"] = block.text.strip()
                yield block
