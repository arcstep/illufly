from typing import Any, Dict, Iterator, List, Optional, Union
from langchain.pydantic_v1 import BaseModel, Field, root_validator
from langchain.memory import ConversationBufferWindowMemory
from ..memory.history import LocalFileMessageHistory, create_session_id
from ..memory.memory_manager import MemoryManager
from ..memory.base import WithMemoryBinding
from .node import ContentNode
from .command import BaseCommand

class ContentTree(BaseModel, BaseCommand):
    """内容管理树。"""

    root_content: Optional[ContentNode] = None
    todo_content: Optional[ContentNode] = None
    memory: Optional[MemoryManager] = None

    class Config:
        arbitrary_types_allowed = True  # 允许任意类型

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # 短期记忆体
        self.memory = MemoryManager(
            # 暂不考虑保存对话历史到磁盘
            # lambda session_id: LocalFileMessageHistory(session_id),
            shorterm_memory = ConversationBufferWindowMemory(return_messages=True, k=20)
        )

        # 初始化参数
        keys = ["auto"]
        for k in keys:
            if k in kwargs:
                setattr(self, k, kwargs[k])

        if self.root_content == None:
            self.root_content = TreeContent(type="root")                
        self.move_focus("START")

    # inherit
    @staticmethod
    def commands(self) -> List[str]:
        return [
            "title", "howto", "text", "words_advice", "children", 
            "ok", "todo", "modi",
        ]

    # inherit
    def call(self, **kwargs):
        command = kwargs['command']
        args = kwargs['args']
        if command == "ok":
            res = self.ok()
        else:
            res = self._cmd_process_content_command(command, args)

        return res

    # 任务游标：
    @property
    def default_focus(self):
        return f'{todo_content.id}#{todo_content.default_scope}'

    def move_focus(self, focus: str) -> str:
        """
        移动到指定节点，默认将位置设定为output。
        """
        if focus == "START":
            self.todo_content = self.root_content
            self.focus = focus
        elif focus == "END":
            self.todo_content = None
            self.focus = focus
        elif focus == None:
            # 没有解析到内容ID
            pass
        else:
            target = self.root_content.get_item_by_id(focus)
            if target:
                self.todo_content = target
                self.focus = f'{target.id}'
            else:
                # 在对象树中无法找到内容ID
                pass

        return self.focus

    def move_focus_auto(self) -> str:
        """
        从root开始遍历所有未完成的节点。
        """
        if self.focus == "END":
            pass
        elif self.focus == "START":
            self.move_focus(self.todo_content.id)
        else:
            next_todo = self.root_content.next_todo()
            if next_todo:
                self.move_focus(next_todo.id)
            else:
                self.focus = "END"
        return self.focus

    def all(self) -> List[Dict[str, str]]:
        """获得所有未完成的内容"""
        # 初始化一个空列表来存储未完成的节点的信息
        all_items = [{
            "id": self.id,
            "is_completed": self.is_completed,
            "type": self.type,
            "words_advice": self.words_advice,
            "title": self.title,
        }]

        # 遍历当前节点的所有子节点
        for child in self.children:
            all_items.extend(child.all())

        # 返回未完成的节点的信息列表
        return all_items

    def todos(self) -> List[Dict[str, str]]:
        """获得所有未完成的内容"""
        # 初始化一个空列表来存储未完成的节点的信息
        todo_items = []

        # 如果当前节点未完成，将其信息添加到列表中
        if not self.is_completed:
            todo_items.append({
                "id": self.id,
                "type": self.type,
                "words_advice": self.words_advice,
                "title": self.title,
            })

        # 遍历当前节点的所有子节点
        for child in self.children:
            todo_items.extend(child.todos())

        # 返回未完成的节点的信息列表
        return todo_items

    def next_todo(self) -> Optional["ContentNode"]:
        """找出下一个等待完成的任务"""
        todos = self.todos()
        for item in todos:
            if item['type'] == 'paragraph':
                content = self.get_item_by_id(item['id'])
                return content
        return None
    
    def get_lines(self, numbers: List[int] = []) -> List[Dict[str, Union[str, int]]]:
        """
        从树形结构中解析出大纲和段落的列表，
        根据children中的排序和树形结构的深度增加一个多层编号，
        例如：
        [
            {"sn":"1",     "title":"xxx", "summarise": "xxx", "text": ""},
            {"sn":"1.1",   "title":"xxx", "summarise": "xxx", "text": ""},
            {"sn":"1.1.1", "title":"xxx", "summarise": "xxx", "text": ""},
            {"sn":"1.1.2", "title":"xxx", "summarise": "xxx", "text": ""},
            {"sn":"1.2",   "title":"xxx", "summarise": "xxx", "text": ""},
            {"sn":"2",     "title":"xxx", "summarise": "xxx", "text": ""},
            {"sn":"2.1",   "title":"xxx", "summarise": "xxx", "text": ""},
            {"sn":"2.2",   "title":"xxx", "summarise": "xxx", "text": ""},
        ]
        """
        
        lines = []
        for i, child in enumerate(self.children, start=1):
            new_numbers = numbers + [i]
            lines.append({
                "id": child.id,
                "sn": generate_sn(new_numbers),
                "type": child.type,
                "is_completed": child.is_completed,
                "words_advice": child.words_advice,
                "title": child.title or "",
                "howto": child.howto or "",
                "summarise": child.summarise or None,
                "text": child.text or "",
                "path": child.path or "",
            })
            lines.extend(child.get_lines(new_numbers))
        return lines

    def get_input(self) -> str:
        """获得提示语输入"""
        output = ""
        if self.summarise:
            output = f"\n  内容摘要 >>> {self.summarise}"

        return f'《{self.title}》\n' \
            + f'总字数要求约{self.words_advice}字；{"已完成" if len(self.todos())==0 else "* 未完成"}。\n' \
            + f'扩写指南 >>> {self.howto}\n' \
            + output

    def get_outlines(self, numbers: List[int] = []) -> List[Dict[str, Union[str, int]]]:
        """获得大纲清单"""
        input = self.get_input()
        lines = [
            f"{x['sn']} {x['title']} \n  扩写指南 >>> {x['howto']}\n  内容摘要 >>> {x['summarise']}"
            for x in self.get_lines(numbers)
        ]
        all_lines = '\n'.join(lines)
        return f"{input}\n{all_lines}"

    def get_text(self, numbers: List[int] = []):
        """获得文字成果"""
        input = self.get_input()
        lines = [f"{line['sn']} {line['title']}\n {line['text']}" for line in self.get_lines(numbers)]
        if self.text:
            return [input] + lines + [self.text]
        else:
            return [input] + lines

    def print_text(self):
        """打印所有行的序号、标题和文字内容"""
        for line in self.get_text():
            print(line)
