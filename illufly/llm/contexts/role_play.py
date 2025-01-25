from .base import BaseContext
from typing import Dict, Any, List

class RolePlayContext(BaseContext):
    """角色扮演上下文
    
    为AI设定特定角色和背景
    """
    def __init__(self, role_description: str, **kwargs):
        super().__init__(**kwargs)
        self.role_description = role_description

    def handle_input_messages(self, messages: List[Dict[str, Any]]):
        """在对话前添加角色描述"""
        return [{'role': 'system', 'content': self.role_description}] + messages 