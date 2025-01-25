from .base import BaseContext
from typing import Dict, Any, List, Callable

class ToolContext(BaseContext):
    """工具调用上下文
    
    管理工具调用历史，支持工具链式调用
    """
    def __init__(self, tools: List[Callable], **kwargs):
        super().__init__(**kwargs)
        self.tools = {tool.__name__: tool for tool in tools}
        self.tool_history = []

    def handle_input_messages(self, messages: List[Dict[str, Any]]):
        """检查是否需要调用工具"""
        last_message = messages[-1]['content']
        if self._needs_tool(last_message):
            tool_name = self._parse_tool_name(last_message)
            tool_result = self._call_tool(tool_name, last_message)
            return [{'role': 'tool', 'content': tool_result}] + messages
        return messages 