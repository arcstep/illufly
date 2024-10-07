import json

from typing import Union, List, Dict, Any
from ..base import BaseAgent

class ToolsManager:
    """
    ToolsManager 基类，用于管理工具相关的功能。

    在实际使用中，tools 参数可能被大模型作为参数引用，也可能被提示语模板引用。
    如果 tools_desc 被提示语模板绑定，则 tools 就从传递给大模型的参数中剔除。
    """

    def __init__(self, tools=None, exec_tool=None, **kwargs):
        self.tools = [
            t if isinstance(t, BaseAgent) else BaseAgent(t)
            for t in (tools or [])
        ]
        self.exec_tool = True if exec_tool is None else exec_tool

    def get_tools(self, tools: List["BaseAgent"]=None):
        _tools = [
            t if isinstance(t, BaseAgent) else BaseAgent(func=t)
            for t in (tools or [])
        ]
        if _tools and (
            not isinstance(_tools, list) or
            not all(isinstance(tool, BaseAgent) for tool in _tools)
        ):
            raise ValueError("tools 必须是 BaseAgent 列表")
        return self.tools + _tools

    def get_tools_name(self, tools: List[BaseAgent]=None):
        return ",".join([a.name for a in self.get_tools(tools)])

    def get_tools_desc(self, tools: List[BaseAgent]=None):
        return [t.tool_desc for t in self.get_tools(tools)]
