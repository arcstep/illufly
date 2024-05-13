from langchain.pydantic_v1 import BaseModel, Field, root_validator
from typing import Any, Dict, Iterator, List, Optional, Union
from statemachine import StateMachine, State
import datetime
import random

def generate_sn(numbers: List[int]) -> str:
    return ".".join(str(number) for number in numbers)

class ContentState(StateMachine):
    """实现基于有限状态机的内容管理"""

    # 定义有限状态机的状态
    #
    # 扩写指南
    init = State("init", initial=True)
    # 完全重新生成：有扩写指南，祖先已完成扩写
    todo = State("todo")
    # 已完成扩写
    done = State("done")
    # 重新生成：已完成扩写，支持锁定部份内容后修改，也可直接确认
    mod = State("mod")
    
    # 定义有限状态机的状态转换
    #
    init_todo = init.to(todo)

    todo_done = todo.to(done)
    done_todo = done.to(todo)

    done_mod = done.to(mod)
    mod_done = mod.to(done)

    mod_todo = mod.to(todo)
    
_INVALID_PROMPT_INPUT = ["title", "words_advice", "howto", "summarise", "text"]

class TreeContent(BaseModel):
    """
    存储内容的树形结构，段落内容保存在叶子节点，而提纲保存在children的列表中。    
    """
    # - item：对象，add_item, get_item_xx 等
    # - content：对象中的属性，update_content 等
    # - prompt_input：对象中扩写依据相关的属性，title, words_advice, howto，使用 set_prompt_input 设置
    # - state：结合FSM反应的对象状态    

    # 内容标识
    id: Optional[int] = 0
    
    # 内容状态管理
    _fsm: Optional["ContentState"] = ContentState()
    
    @property
    def state(self):
        return _fsm.current_state.id
    
    @property
    def is_completed(self):
        return self.state == 'done'
    
    def ok(self, request = Dict[str, Any]):
        if self.state == "init":
            if "总字数要求" not in item or "标题名称" not in item or "扩写指南" not in item:
                raise(BaseException("缺少必要的字段：标题名称 | 总字数要求 | 扩写指南"))

            self.title = request["标题名称"]
            self.words_advice = request["总字数要求"]
            self.howto = request["扩写指南"]
            
            self._fsm.init_todo()

        elif self.state == "todo":
            if self.type == "outline":
                # 删除旧的子项，逐个添加新的子项
                self.children = []
                for item in request['大纲列表']:
                    if "总字数要求" not in item or "标题名称" not in item or "扩写指南" not in item:
                        raise(BaseException("缺少必要的字段：标题名称 | 总字数要求 | 扩写指南"))

                    self.add_item(
                        words_advice = item['总字数要求'],
                        title = item['标题名称'],
                        howto = item['扩写指南'],
                        is_completed = False,
                    )
                # print("-"*20, "Outlines Done for", self.id, "-"*20)
            elif self.type == "paragraph":
                if "内容摘要" not in item or "详细内容" not in item:
                    raise(BaseException("缺少必要的字段：内容摘要 | 详细内容"))

                if "内容摘要" in request:
                    self.summarise = request["内容摘要"]
                if "详细内容" in request:
                    self.text = request["详细内容"]
            else:
                raise(BaseException(f"No Type {self.type} for id {self.id}:"))

            self._fsm.todo_done()

        elif self.state == "mod":
            self._fsm.mod_done()

            raise(BaseException("Action for [mod] Not Implement"))

        else:
            raise BaseException("Error State for [ok] command:", self.state)

    type: Optional[str] = "paragraph"

    # 扩写指南
    words_advice: Optional[int] = None
    title: Optional[str] = None
    howto: Optional[str] = None
    # 段落
    summarise: Optional[str] = None
    text: Optional[str] = None
    # 提纲
    children: List["TreeContent"] = []

    # 祖先
    parent: Optional["TreeContent"] = None
    root: Optional["TreeContent"] = None

    # root_children_counter 仅根对象有效
    root_children_counter: Optional[int] = 0
    
    # 设置提示语输入
    def set_prompt_input(k: str, v: str):
        """
        修改创作依据将引起状态变化。
        """
        if k in _INVALID_PROMPT_INPUT and v != None:
            if self.state == "done":
                self._fsm.done_mod()
            return setattr(self, k, v)
        else:
            raise BaseException("No prompt input KEY: ", k)

    def get_prompt_input(k: str):
        if k in _INVALID_PROMPT_INPUT:
            return getattr(self, k)
        else:
            raise BaseException("No prompt input KEY: ", k)

    # 保存路径
    path: Optional[str] = None

    def load(self):
        pass  # 实现加载逻辑

    def save(self):
        pass  # 实现保存逻辑

    def add_item(self, **kwargs):
        if self.children == None:
            self.children = []

        # 子内容的ID自动递增
        root = self.root or self
        root.root_children_counter += 1
        
        kwargs.update({
            "id": root.root_children_counter,
            "parent": self,
            "root": root,
        })
        content = TreeContent(**kwargs)
        content.init_todo()

        self.children.append(content)
        self.type = "outline"

        return content

    def get_item_by_id(self, id: Union[int, str]) -> Optional["TreeContent"]:
        """递归查询并返回指定id的Content"""

        if id == None:
            return None

        if isinstance(id, str):
            id = int(id)
            
        if self.id == id:
            return self

        for child in self.children or []:
            if child.id == id:
                return child
            if len(self.children) > 0:
                found = child.get_item_by_id(id)
                if found:
                    return found

        return None

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

    def next_todo(self) -> Optional["TreeContent"]:
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
