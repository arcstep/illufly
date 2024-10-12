from typing import List, Union, Dict, Any
from ......io import EventBlock, NewLineBlock
from ....message import Messages
from ..base import BaseAgent

class BaseToolCalling:
    def __init__(
        self,
        short_term_memory: Messages,
        long_term_memory: Messages,
        tools_to_exec: List[BaseAgent],
        exec_tool: bool=True
    ):
        self.short_term_memory = short_term_memory
        self.long_term_memory = long_term_memory
        self.tools_to_exec = tools_to_exec
        self.exec_tool = exec_tool

    def remember_response(self, response: Union[str, List[dict]]):
        """
        将回答添加到记忆中。
        """
        if response:
            if isinstance(response, str):
                new_memory = Messages([("assistant", response)]).to_list()
            else:
                new_memory = response

            self.long_term_memory.extend(new_memory)
            return new_memory
        else:
            return []

    def extract_tools_call(self, text: str) -> List[Dict[str, Any]]:
        pass

    def handle_tools_call(self, final_tools_call, kwargs):
        pass

    async def async_handle_tools_call(self, final_tools_call, kwargs):
        pass

    def execute_tool(self, tool, kwargs):
        for struct_tool in self.tools_to_exec:
            if tool.get('function', {}).get('name') == struct_tool.name:
                tool_args = struct_tool.parse_arguments(tool['function']['arguments'])
                tool_resp = ""

                tool_func_result = struct_tool.call(**tool_args)
                for x in tool_func_result:
                    if isinstance(x, EventBlock):
                        if x.block_type == "tool_resp_final":
                            tool_resp = x.text
                        elif x.block_type == "chunk":
                            tool_resp += x.text
                        yield x
                    else:
                        tool_resp += x
                        yield EventBlock("tool_resp_chunk", x)
                yield NewLineBlock()
                yield EventBlock("tool_resp_final", tool_resp)

    async def async_execute_tool(self, tool, kwargs):
        for struct_tool in self.tools_to_exec:
            if tool.get('function', {}).get('name') == struct_tool.name:
                tool_args = struct_tool.parse_arguments(tool['function']['arguments'])
                tool_resp = ""

                tool_func_result = struct_tool.async_call(**tool_args)
                async for x in tool_func_result:
                    if isinstance(x, EventBlock):
                        if x.block_type == "tool_resp_final":
                            tool_resp = x.text
                        elif x.block_type == "chunk":
                            tool_resp += x.text
                        yield x
                    else:
                        tool_resp += x
                        yield EventBlock("tool_resp_chunk", x)

                yield NewLineBlock()
                yield EventBlock("tool_resp_final", tool_resp)
