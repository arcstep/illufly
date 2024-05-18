from typing import Any, Dict, Iterator, List, Optional, Union
from dotenv import find_dotenv
import os
import json

class ContentSerialize():
    """
    支持序列化的属性存储结构
    
    args:
    - project_id 项目的ID，在对多个项目同时操作时，
    """

    def __init__(
        self,
        project_id: str=None,
        index: int=0,
        parent: "ContentSerialize"=None,
        **kwargs
    ):
        """
        初始化方法
        """
        self._project_id = project_id or "default"
        self._index = index
        self._parent = parent

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
        counter = 0

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

    def get_project_folder(self):
        """从环境变量中获得项目的存储目录"""
        return os.getenv("TEXTLONG_FOLDER") or "textlong_data"

    def sort_key(self, filename: str) -> List[int]:
        return list(map(int, filename[:-5].split('.')))

    def load(self):
        """加载内容及其所有子节点"""

        project_folder = self.get_project_folder()
        contents_dir = os.path.join(project_folder, self._project_id, "contents")

        # 检查目录是否存在
        if not os.path.exists(contents_dir):
            raise FileNotFoundError(f"目录 {contents_dir} 不存在")

        # 读取目录下的所有文件
        all_files = sorted(os.listdir(contents_dir), key=self.sort_key)
        print(all_files)
        for filename in all_files:
            basename = os.path.basename(filename)
            if filename.endswith(".json") and basename.startswith(self.id) and basename != f'{self.id}.json':
                with open(os.path.join(contents_dir, filename), 'r') as f:
                    data = json.load(f)

                # 从数据中创建 ContentSerialize 对象
                item_id = data.get('id')
                if item_id is None:
                    raise ValueError(f"文件 {filename} 中的数据没有 'id' 字段")

                # 分割 id，获取父节点和当前节点的索引
                id_parts = item_id.split('.')
                parent_id = '.'.join(id_parts[:-1]) if len(id_parts) > 1 else None
                index = int(id_parts[-1])

                # 查找父节点
                parent = self.get_item_by_id(parent_id) if parent_id else self

                # 创建新的 ContentSerialize 对象并添加到父节点的 _children 字典中
                node = self.__class__(project_id=self._project_id, index=index, parent=parent, **data)
                parent._children[index] = node

        return self

    def dump(self):
        """导出内容及其所有子节点"""

        project_folder = self.get_project_folder()
        for item in self.all_content:
            print(item)
            path = os.path.join(project_folder, self._project_id, "contents", item['id']) + ".json"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                json.dump(item, f, indent=4)

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

    def add_item(self, item_class=None, **kwargs):
        if item_class is None:
            item_class = self.__class__

        new_kwargs = {} if kwargs is None else kwargs
        index = max(self._children) + 1 if self._children else 1
        new_kwargs.update({
            "project_id": self._project_id,
            "index": index,
            "parent": self,
        })

        node = item_class(**new_kwargs)
        self._children[index] = node

        return node
