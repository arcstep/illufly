import json

from typing import Union, List, Dict, Any
from ..tool import ToolAgent
from ..tool_ability import ToolAbility

class ToolsManager:
    """
    ToolsManager 基类，用于管理工具相关的功能。
    """

    def __init__(self, tools=None, exec_tool=None, **kwargs):
        self.tools = [
            t if isinstance(t, ToolAbility) else ToolAgent(t)
            for t in (tools or [])
        ]
        self.exec_tool = True if exec_tool is None else exec_tool

    def get_tools(self, tools: List["ToolAbility"]=None):
        _tools = [
            t if isinstance(t, ToolAbility) else ToolAgent(t)
            for t in (tools or [])
        ]
        if _tools and (
            not isinstance(_tools, list) or
            not all(isinstance(tool, ToolAbility) for tool in _tools)
        ):
            raise ValueError("tools 必须是 ToolAbility 列表")
        return self.tools + _tools

    def get_tools_name(self, tools: List[ToolAbility]=None):
        return ",".join([a.name for a in self.get_tools(tools)])

    def get_tools_desc(self, tools: List[ToolAbility]=None):
        return [t.tool_desc for t in self.get_tools(tools)]

    def get_tools_instruction(self, tools: List[ToolAbility]=None):
        """
        描述工具调用的具体情况。
        """
        action_output = {
            "index": "integer: index of selected function",
            "function": {
                "name": "(string): 填写选中工具的参数名称",
                "parameters": "(json): 填写具体参数值"
            }
        }
        name_list = ",".join([a.name for a in self.get_tools(tools)])
        example = '\n'.join([
            '**工具函数输出示例：**',
            '```json',
            '[{"index": 0, "function": {"name": "get_current_weather", "parameters": "{\"location\": \"广州\"}"}},',
            '{"index": 1, "function": {"name": "get_current_weather", "parameters": "{\"location\": \"上海\"}"}}]',
            '```'
        ])

        output = f'```json <tools-calling>\n[{json.dumps(action_output, ensure_ascii=False)}]\n```'

        return f'从列表 [{name_list}] 中选择一个或多个funciton，并按照下面的格式输出函数描述列表，描述每个函数的名称和参数：\n{output}\n{example}'
