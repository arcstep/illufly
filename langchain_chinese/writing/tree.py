from typing import Any, Dict, Iterator, List, Optional, Union
from langchain.memory import ConversationBufferWindowMemory
from ..memory.memory_manager import MemoryManager
from .node import ContentNode
from .command import BaseCommand

class ContentTree(BaseCommand):
    """内容管理树。"""

    def __init__(
        self,
        todo_node: Optional[ContentNode] = None,
        memory: Optional[MemoryManager] = None,
        **kwargs
    ):
        super().__init__(**kwargs)

        self.todo_node = TreeContent() if todo_node == None else todo_node
        self.memory = memory

    @property
    def root(self):
        return self.todo_node.root
    
    @property
    def focus(self):
        return self.todo_node.id

    # inherit
    def commands(self) -> List[str]:
        return []

    # inherit
    def parse(self, user_said: str) -> tuple:
        if user_said is None:
            return {"id": None, "command": None, "args": None}

        pattern = r'^\s*(?:<([\w.-]+)>)?\s*(' + '|'.join(self.__class__.commands()) + r')?\s*(.*)$'
        match = re.match(pattern, user_said, re.IGNORECASE)

        if match:
            content_id, command, args = match.groups()

        return {"id": content_id, "command": command, "args": args}

    # inherit
    def invoke(self, user_said: str) -> Any:
        resp = self.parser(user_said)

        if resp and resp['command'] in self.commands():
            resp['reply'] = self.call(**resp)
        else:
            if resp['id'] == None:
                obj = self.todo_content
            else:
                obj = self.root_content.get_item_by_id(resp['id'])
            if obj and resp['command'] in obj.commands:
                resp['reply'] = obj.call(**resp)

        return resp

    # inherit
    def call(self, command, **kwargs):
        resp = self.parser(user_said)
        resp['reply'] = None

        return resp

    def move_focus(self, id: str) -> str:
        """
        移动到指定节点。
        """
        target = self.root.get_item_by_id(id)
        if target:
            self.todo_node = target
        else:
            # 在对象树中无法找到内容ID
            raise BaseException("Invalid content ID:", id)

        return self.todo_node.id

    def move_focus_auto(self) -> str:
        """
        从root开始遍历所有未完成的节点。
        """
        next_todo = self.root.not_complete_child
        if next_todo:
            self.move_focus(next_todo.id)
            return True
        else:
            return False

