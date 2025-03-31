import json

from typing import Union, List, Dict, Any
from ..base import BaseAgent
from .tools_calling import BaseToolCalling, ToolCall, Plans, SubTask

class ToolsManager:
    """
    ToolsManager 基类，用于管理工具相关的功能。

    在实际使用中, tools 参数可能被大模型作为参数引用，也可能被提示语模板引用。
    如果 tools_desc 被提示语模板绑定，则 tools 就从传递给大模型的参数中剔除。

    tools_handlers 是工具处理器的列表，每个处理器可以处理一种工具调用行为。

    tools_behavior 是工具处理器的处理行为列表，有三种值：
    - parse: 仅解析工具回调, 不执行
    - parse-execute: 解析工具回调后执行, 然后停止
    - parse-execute-continue: 解析工具回调, 执行工具, 然后继续调用模型
    """
    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "tools": "工具列表",
            "tools_handlers": "工具处理器列表",
            "tools_behavior": "工具处理行为, 包括 parse-execute, parse-execute-continue, parse-continue-execute 三种行为",
        }

    def __init__(
        self,
        tools=None,
        tools_handlers: List[BaseToolCalling]=None,
        tools_behavior: str=None
    ):
        self.tools = [
            t if isinstance(t, BaseAgent) else BaseAgent(t)
            for t in (tools or [])
        ]
        self.tools_handlers = tools_handlers or [ToolCall(), Plans(), SubTask()]
        for h in self.tools_handlers:
            h.reset(self.tools)

        self.tools_behavior = tools_behavior or "parse-execute-continue"

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
