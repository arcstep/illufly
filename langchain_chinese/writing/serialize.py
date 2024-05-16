from typing import Any, Dict, Iterator, List, Optional, Union

class ContentSerialize():
    """支持序列化的属性存储结构"""

    def __init__(
        self,
        project_id: str = None,
        index: int = 0,
        parent: "ContentSerialize" = None,
    ):
        """
        初始化方法
        """
        self._project_id = project_id        
        self._index = index
        self._parent = parent

        self._path: str = None
        self._children: Dict[str, "ContentSerialize"] = {}

    @property
    def id(self):
        if self._parent == None:
            return f'{self._index}'
        else:
            return ".".join([self._parent.id, f'{self._index}'])

    @property
    def parent(self):
        return self._parent

    @property
    def root(self):
        root = self
        max_counter = 1e4

        while root._parent:
            root = root._parent
            counter += 1
            if counter > max_counter:
                raise BaseException("父对象嵌套过多！")

        return root

    @property
    def content(self) -> Dict[str, Union[str, int]]:
        """
        内容清单。
        """
        return {
            "id": self.id,
            "type": self.type,
            "state": self.state,
            "is_complete": self.is_complete,
            "path": self.path or "",
        }        

    # 扁平化列表的内容列表
    @property
    def all_content(self) -> List[Dict[str, Union[str, int]]]:
        """
        从树形结构中转化为扁平化列表的内容清单列表。
        """
        items = [self.content]
        for child in self._children.values():
            items.extend(child.all_content)
        return items

    def __str__(self):
        str_children = [f"<id:{obj.id}>" for obj in self._children.values()]
        return f"<{self.__class__.__name__} id:{self.id}, children:{str_children}>"

    def load(self):
        pass  # 实现加载逻辑

    def save(self):
        pass  # 实现保存逻辑

    def get_item_by_id(self, id: str) -> Optional["ContentSerialize"]:
        if id is None:
            return None

        indexs = [int(counter) for counter in id.split(".")]
        if indexs[0] != self._index:
            raise BaseException("Invalid id: 无法在当前对象的子项列表中查询该ID!")

        current_item = self

        if len(indexs) > 1:
            for counter in indexs[1:]:
                current_item = current_item._children.get(counter)
            
                if current_item is None:
                    return None

        return current_item

    def add_item(self, **kwargs):
        new_kwargs = {} if kwargs is None else kwargs
        index = max(self._children) + 1 if self._children else 1
        new_kwargs.update({
            "project_id": self._project_id,
            "index": index,
            "parent": self,
        })

        node = ContentSerialize(**new_kwargs)
        self._children[index] = node

        return node
