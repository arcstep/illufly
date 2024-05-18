from typing import Any, Dict, Iterator, List, Optional, Union
from dotenv import find_dotenv
from .node import ContentNode
from .serialize import ContentSerialize
import os
import json

_NODES_FOLDER_NAME = "__NODES__"
_TEMPLATES_FOLDER_NAME = "__TEMPLATES__"
_CONTENTS_FOLDER_NAME = "__CONTENTS__"
_PROMPTS_FOLDER_NAME = "__PROMPTS__"

def get_project_folder():
    """从环境变量中获得项目的存储目录"""
    return os.getenv("TEXTLONG_FOLDER") or "textlong_data"

def list_projects():
    """列举有哪些可用的project_id"""
    projects = []
    project_folder = get_project_folder()
    all_items = os.listdir(project_folder)

    for item in all_items:
        item_path = os.path.join(project_folder, item)
        if os.path.isdir(item_path) and not item.startswith('.'):
            contents_dir = os.path.join(item_path, _NODES_FOLDER_NAME)
            if os.path.exists(contents_dir):
                projects.append(item)

    return projects

def load(cls, project_id: str, id="0"):
    """
    加载内容及其所有子节点。
    load操作被设计为类方法，而对应的dump被设计为实例方法。
    """
    root = None
    project_folder = get_project_folder()
    contents_dir = os.path.join(project_folder, project_id, _NODES_FOLDER_NAME)

    if not os.path.exists(contents_dir):
        raise FileNotFoundError(f"目录 {contents_dir} 不存在")

    # 读取目录下的所有文件，按去掉".json"后的文件名排序
    sort_key = lambda filename : list(map(int, filename[:-5].split('.')))
    all_files = sorted(os.listdir(contents_dir), key=sort_key)

    for filename in all_files:
        basename = os.path.basename(filename)
        if filename.endswith(".json"):
            with open(os.path.join(contents_dir, filename), 'r') as f:
                data = json.load(f)

            item_id = data.get('id')
            if item_id is None:
                raise ValueError(f"文件 {filename} 中的数据没有 'id' 字段")

            id_parts = item_id.split('.')
            index = int(id_parts[-1])

            if basename == f'{id}.json':
                # 写入根节点
                root = cls(project_id=project_id, index=index, parent=None, **data)
            elif root:
                parent_id = '.'.join(id_parts[:-1]) if len(id_parts) > 1 else None
                parent = root.get_item_by_id(parent_id)

                # 写入子节点
                node = cls(project_id=project_id, index=index, parent=parent, **data)
                parent._children[index] = node
            else:
                raise ValueError(f"根节点 {id} 还没有被创建")

    return root

def dump(node: ContentSerialize):
    """
    导出内容及其所有子节点。
    dump被设计为实例方法，这会更方便操作。
    """
    if not node or len(node.all_content) == 0:
        print("⚠️ Nothing to DUMP !!")
        return False

    project_folder = get_project_folder()

    for item in node.all_content:
        path = os.path.join(project_folder, node._project_id, _NODES_FOLDER_NAME, item['id']) + ".json"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(item, f, indent=4, ensure_ascii=False)
    
    return True

