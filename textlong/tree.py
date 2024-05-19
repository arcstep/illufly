from typing import Any, Dict, Iterator, List, Optional, Union
from .node import ContentNode
from .command import BaseCommand

class ContentTree(BaseCommand):
    """内容管理树。"""

    def __init__(self, node=None, **kwargs):
        BaseCommand.__init__(self)
        if node:
            self.todo_node = node
        else:
            self.todo_node = ContentNode(**kwargs)

    @property
    def root(self):
        return self.todo_node.root

    # inherit
    @property
    def default_command(self) -> str:
        return self.todo_node.default_command

    # inherit
    @property
    def commands(self) -> List[str]:
        return ["move", "todo", "draft", "outlines", "nodes", "texts"] + self.todo_node.commands

    # inherit
    def call(self, command, args, **kwargs):
        if command == 'move' and args:
            # 转移到新的指定对象
            obj = self.root.get_item_by_id(args)
            self.todo_node = obj or self.todo_node
            return obj != None

        elif command == 'todo':
            # 转移到新的待完成对象
            if self.todo_node.is_complete:
                obj = self.root.find_not_complete_node()
                if obj:
                    self.todo_node = obj
            else:
                obj = self.todo_node
            return obj.id if obj else None

        elif command == 'draft':
            # 转移到新的草稿对象
            if not self.todo_node.is_draft:
                obj = self.root.find_draft_node()
                if obj:
                    self.todo_node = obj
            else:
                obj = self.todo_node
            return obj.id if obj else None
        elif command == "nodes":
            return self.root.all_content
        elif command == "outlines":
            return self.root.get_outlines()
        elif command == "texts":
            return self.root.get_texts()
        else:
            return self.todo_node.call(command, args, **kwargs)

