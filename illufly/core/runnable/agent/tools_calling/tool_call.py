from typing import List, Dict, Any
from .base import BaseToolCalling
from .....io import EventBlock, NewLineBlock
import json

class ToolCall(BaseToolCalling):

    def extract_tools_call(self, text: str) -> List[Dict[str, Any]]:
        tool_calls = []
        start_marker = "<tool_call>"
        end_marker = "</tool_call>"
        start = text.find(start_marker)
        while start != -1:
            end = text.find(end_marker, start)
            if end != -1:
                tool_call_json = text[start + len(start_marker):end]
                try:
                    tool_call = json.loads(tool_call_json)
                    tool_calls.append({
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
        return tool_calls

    def handle_tools_call(self, final_tool_call):
        if self.exec_tool:
            for block in self.execute_tool(final_tool_call):
                if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                    tool_resp = block.text
                    tool_resp_message = [
                        {
                            "role": "user",
                            "content": f'<tool_resp>{tool_resp}</tool_resp>'
                        }
                    ]
                    self.short_term_memory.extend(tool_resp_message)
                    self.long_term_memory.extend(tool_resp_message)
                yield block

    async def async_handle_tools_call(self, final_tool_call):
        if self.exec_tool:
            async for block in self.async_execute_tool(final_tool_call):
                if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                    tool_resp = block.text
                    tool_resp_message = [
                        {
                            "role": "user",
                            "content": f'<tool_resp>{tool_resp}</tool_resp>'
                        }
                    ]
                    self.short_term_memory.extend(tool_resp_message)
                    self.long_term_memory.extend(tool_resp_message)
                yield block
