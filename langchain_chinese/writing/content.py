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
    
class TreeContent(BaseModel):
    """
    存储内容的树形结构，段落内容保存在叶子节点，而提纲保存在children不为空的节点。
    """

    # 内容标识
    id: Optional[str] = None
    type: Optional[str] = "paragraph"
    is_completed: Optional[bool] = False

    # 扩写依据
    words_advice: Optional[int] = 500
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
