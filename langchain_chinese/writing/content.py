from langchain.pydantic_v1 import BaseModel, Field, root_validator
from typing import Any, Dict, Iterator, List, Optional, Union
import datetime
import random

global_id = 0

def create_content_id():
    global global_id
    now = datetime.datetime.now()
    random_digits = random.randint(100, 999)  # 生成一个四位的随机数

    # 更新 global_id
    global_id += 1
    if global_id > 99999:
        global_id = 0
    global_id_str = str(global_id).zfill(5)

    return now.strftime(f"%Y%m%d.%H%M%S.{global_id_str}.{random_digits}")

def generate_sn(numbers: List[int]) -> str:
    return ".".join(str(number) for number in numbers)
    
class TreeContent(BaseModel):
    """
    存储内容的树形结构，段落内容保存在叶子节点，而提纲保存在children不为空的节点。
    """

    # 内容标识  
    id: Optional[str] = None
    type: Optional[str] = "paragraph"
    is_completed: Optional[bool] = False

    # 扩写依据
    words_advice: Optional[int] = None
    title: Optional[str] = None
    howto: Optional[str] = None
    summarise: Optional[str] = None
    text: Optional[str] = None

    # 提纲扩展
    children: List["TreeContent"] = []

    # 保存路径
    path: Optional[str] = None

    def load(self):
        pass  # 实现加载逻辑

    def save(self):
        pass  # 实现保存逻辑

    @root_validator
    def auto_generate_id(cls, value):
        if value['id'] is None:
            value['id'] = create_content_id()   
        return value

    def add_item(self, content: "TreeContent"):
        if self.children is None:
            self.children = []
        self.children.append(content)
        self.type = "outline"

        return content.id

    def get_item_by_id(self, id: str) -> Optional["TreeContent"]:
        """递归查询并返回指定id的Content"""
        if id == None:
            return None
            
        if self.id == id:
            return self

        for child in self.children or []:
            if child.id == id:
                return child
            if self.type == "outline":
                found = child.get_item_by_id(id)
                if found:
                    return found

        return None

    def all_todos(self) -> List[Dict[str, str]]:
        """获得所有未完成的内容"""
        # 初始化一个空列表来存储未完成的节点的信息
        todos = []

        # 如果当前节点未完成，将其信息添加到列表中
        if not self.is_completed:
            todos.append({
                "id": self.id,
                "type": self.type,
                "words_advice": self.words_advice,
                "title": self.title,
            })

        # 遍历当前节点的所有子节点
        for child in self.children:
            todos.extend(child.all_todos())

        # 返回未完成的节点的信息列表
        return todos

    def next_todo(self) -> Optional["TreeContent"]:
        """找出下一个等待完成的任务"""
        todos = self.all_todos()
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
        output = ""
        if self.summarise:
            output = f"\n  内容摘要 >>> {self.summarise}"

        return f'《{self.title}》\n' \
            + f'总字数要求约{self.words_advice}字；{"已完成" if len(self.all_todos())==0 else "尚未完成"}。\n' \
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
        input = self.get_input()
        lines = [f"{line['sn']} {line['title']}\n {line['text']}" for line in self.get_lines(numbers)]
        if self.text:
            return [input] + lines + self.text
        else:
            return [input] + lines

    def print_text(self):
      """打印所有行的序号、标题和文字内容"""
      for line in self.get_text():
          print(line)

