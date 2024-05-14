from typing import Any, Dict, Iterator, List, Optional, Union

class ContentSerialize():
    """支持序列化的属性存储结构"""

    def __init__(self, **kwargs):
        self._id_counter: int = 0
        self._path: Optional[str] = None
        self._parent: Optional["ContentSerialize"] = None
        self._children: Dict[str, "ContentSerialize"] = {}

        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def id(self):
        if self._parent == None:
            return f'{self._id_counter}'
        else:
            return ".".join([self._parent.id, f'{self._id_counter}'])

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

        id_counters = [int(counter) for counter in id.split(".")]
        if id_counters[0] != self._id_counter:
            raise BaseException("Invalid id: 无法在当前对象的子项列表中查询该ID!")

        current_item = self

        if len(id_counters) > 1:
            for counter in id_counters[1:]:
                current_item = current_item._children.get(counter)
            
                if current_item is None:
                    return None

        return current_item

    def add_item(self, **kwargs):
        new_kwargs = {} if kwargs is None else kwargs
        id_counter = max(self._children) + 1 if self._children else 1
        new_kwargs.update({
            "_id_counter": id_counter,
            "_parent": self,
        })

        content = ContentSerialize(**new_kwargs)
        self._children[id_counter] = content

        return content
