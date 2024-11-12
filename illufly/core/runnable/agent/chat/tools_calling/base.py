from typing import List, Union, Dict, Any
from ......io import EventBlock, NewLineBlock
from ....message import Messages
from ...base import BaseAgent

class BaseToolCalling:
    def __init__(
        self,
        tools_to_exec: List[BaseAgent] = None,
        steps: List[Any] = None
    ):
        self.tools_to_exec = tools_to_exec
        self.steps = steps or []

    def reset(self, tools_to_exec: List[BaseAgent]=None):
        self.tools_to_exec = tools_to_exec or self.tools_to_exec
        self.steps.clear()

    @property
    def completed_work(self):
        """
        返回所有步骤的完成情况。
        """
        return "\n".join([str(step) for step in self.steps])

    def extract_tools_call(self, text: str) -> List[Dict[str, Any]]:
        """
        解析工具回调。

        text 必须为包含工具回调描述的字符串。
        """
        return []
    def handle(self, final_tools_call):
        """
        处理工具回调。

        final_tools_call 是一组自定义的工具解析结果，这可能是工具回调描述、计划描述的列表，也可以是DAG描述等形式。
        """
        return []

    async def async_handle(self, final_tools_call):
        return []

    def execute_tool(self, tool):
        """
        执行工具回调。

        tool 必须具有如下 Python 字典格式：
        {
            "function":
                "name": function_name
                "arguments": arguments_json
        }
        其中 function_name 必须为 self.tools_to_exec 中的某个 name 属性，
        arguments 则必须为一个可转换为 Python 字典的 JSON 字符串。
        """
        if not self.tools_to_exec:
            yield self.create_event_block("warn", f"tools_to_exec is empty")
            return

        for struct_tool in self.tools_to_exec:
            if tool.get('function', {}).get('name') == struct_tool.name:
                yield self.create_event_block("agent", struct_tool.name)
                tool_args = struct_tool.parse_arguments(tool['function']['arguments'])
                tool_resp = ""

                if isinstance(tool_args, dict):
                    tool_func_result = struct_tool.call(**tool_args)
                elif isinstance(tool_args, list):
                    tool_func_result = struct_tool.call(*tool_args)
                else:
                    yield self.create_event_block("action_parse_failed", tool_args)
                for x in tool_func_result:
                    if isinstance(x, EventBlock):
                        if x.block_type == "final_tool_resp":
                            tool_resp = x.text
                        elif x.block_type == "chunk":
                            x.block_type = "tool_resp_chunk"
                            tool_resp += x.text
                        elif x.block_type == "text":
                            x.block_type = "tool_resp_text"
                            tool_resp += x.text
                        yield x
                    else:
                        tool_resp += x
                        yield self.create_event_block("tool_resp_chunk", x)
                yield NewLineBlock()
                if tool_resp:
                    yield self.create_event_block("final_tool_resp", tool_resp)
                return

        yield self.create_event_block("warn", f"tool {tool} not found")
            

    async def async_execute_tool(self, tool):
        for struct_tool in self.tools_to_exec:
            if tool.get('function', {}).get('name') == struct_tool.name:
                yield self.create_event_block("agent", struct_tool.name)
                tool_args = struct_tool.parse_arguments(tool['function']['arguments'])
                tool_resp = ""

                if isinstance(tool_args, dict):
                    tool_func_result = struct_tool.async_call(**tool_args)
                elif isinstance(tool_args, list):
                    tool_func_result = struct_tool.async_call(*tool_args)
                else:
                    yield self.create_event_block("action_parse_failed", tool_args)
                async for x in tool_func_result:
                    if isinstance(x, EventBlock):
                        if x.block_type == "final_tool_resp":
                            tool_resp = x.text
                        elif x.block_type == "chunk":
                            x.block_type = "tool_resp_chunk"
                            tool_resp += x.text
                        elif x.block_type == "text":
                            x.block_type = "tool_resp_text"
                            tool_resp += x.text
                        yield x
                    else:
                        tool_resp += x
                        yield self.create_event_block("tool_resp_chunk", x)

                yield NewLineBlock()
                if tool_resp:
                    yield self.create_event_block("final_tool_resp", tool_resp)
