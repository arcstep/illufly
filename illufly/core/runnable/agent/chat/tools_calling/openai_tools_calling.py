from typing import List
from ......io import EventBlock, NewLineBlock
from ....message import Messages
from .base import BaseToolCalling
import json

class OpenAIToolsCalling(BaseToolCalling):
    """
    OpenAI 风格工具调用。
    """
    def handle(self, final_tools_call:str, short_term_memory:Messages, long_term_memory:Messages):
        # 由于 OpenAI 风格工具回调是从文本之外的参数返回的，因此额外追加一次 EventBlock
        final_tools_call_text = json.dumps(final_tools_call, ensure_ascii=False)
        yield NewLineBlock()
        yield EventBlock("final_tools_call", final_tools_call_text)

        for index, tool in enumerate(final_tools_call):
            tools_call_message = [{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool]
            }]

            if self.tools_to_exec:
                # 记忆追加
                short_term_memory.extend(tools_call_message)
                long_term_memory.extend(tools_call_message)

                for block in self.execute_tool(tool):
                    if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                        tool_resp = block.text
                        tool_resp_message = [{
                            "tool_call_id": tool['id'],
                            "role": "tool",
                            "name": tool['function']['name'],
                            "content": tool_resp
                        }]
                        # 短期记忆追加
                        short_term_memory.extend(tool_resp_message)
                        # 长期记忆追加
                        long_term_memory.extend(tool_resp_message)
                    yield block

    async def async_handle(self, final_tools_call: str, short_term_memory: Messages, long_term_memory: Messages):
        final_tools_call_text = json.dumps(final_tools_call, ensure_ascii=False)
        yield EventBlock("final_tools_call", final_tools_call_text)

        for index, tool in enumerate(final_tools_call):
            tools_call_message = [{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool]
            }]
            if self.tools_to_exec:
                # 记忆追加
                short_term_memory.extend(tools_call_message)
                long_term_memory.extend(tools_call_message)

                async for block in self.async_execute_tool(tool):
                    if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                        tool_resp = block.text
                        tool_resp_message = [{
                            "tool_call_id": tool['id'],
                            "role": "tool",
                            "name": tool['function']['name'],
                            "content": tool_resp
                        }]
                        # 短期记忆追加
                        short_term_memory.extend(tool_resp_message)
                        # 长期记忆追加
                        long_term_memory.extend(tool_resp_message)
                    yield block    