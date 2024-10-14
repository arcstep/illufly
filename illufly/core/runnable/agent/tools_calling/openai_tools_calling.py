from typing import List
from .....io import EventBlock, NewLineBlock
from .base import BaseToolCalling
import json

class OpenAIToolsCalling(BaseToolCalling):
    def handle(self, final_tools_call):
        final_tools_call_text = json.dumps(final_tools_call, ensure_ascii=False)
        yield NewLineBlock()
        yield EventBlock("tools_call_final", final_tools_call_text)

        for index, tool in enumerate(final_tools_call):
            tools_call_message = [{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool]
            }]

            if self.tools_to_exec:
                # 记忆追加
                self.short_term_memory.extend(tools_call_message)
                self.long_term_memory.extend(tools_call_message)

                for block in self.execute_tool(tool):
                    if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                        tool_resp = block.text
                        tool_resp_message = [{
                            "tool_call_id": tool['id'],
                            "role": "tool",
                            "name": tool['function']['name'],
                            "content": tool_resp
                        }]
                        # 短期记忆追加
                        self.short_term_memory.extend(tool_resp_message)
                        # 长期记忆追加
                        self.long_term_memory.extend(tool_resp_message)
                    yield block

    async def async_handle(self, final_tools_call):
        final_tools_call_text = json.dumps(final_tools_call, ensure_ascii=False)
        yield EventBlock("tools_call_final", final_tools_call_text)

        for index, tool in enumerate(final_tools_call):
            tools_call_message = [{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool]
            }]
            if self.tools_to_exec:
                # 记忆追加
                self.short_term_memory.extend(tools_call_message)
                self.long_term_memory.extend(tools_call_message)

                async for block in self.async_execute_tool(tool):
                    if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                        tool_resp = block.text
                        tool_resp_message = [{
                            "tool_call_id": tool['id'],
                            "role": "tool",
                            "name": tool['function']['name'],
                            "content": tool_resp
                        }]
                        # 短期记忆追加
                        self.short_term_memory.extend(tool_resp_message)
                        # 长期记忆追加
                        self.long_term_memory.extend(tool_resp_message)
                    yield block    