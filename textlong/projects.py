from typing import Any, Dict, Iterator, List, Optional, Union
from dotenv import find_dotenv
from .node import ContentNode
from .serialize import ContentSerialize
from .config import (
    get_textlong_folder,
    _NODES_FOLDER_NAME,
    _PROMPTS_FOLDER_NAME,
    _CONTENTS_FOLDER_NAME,
)
from .prompts.hub import load_chat_prompt, save_chat_prompt
from .prompts.writing_prompt import (
    create_writing_help_prompt,
    create_writing_init_prompt,
    create_writing_todo_prompt,
)

import os
import json
import datetime
import random

def list_projects():
    """列举有哪些可用的project_id"""
    projects = []
    root_folder = get_textlong_folder()
    all_items = os.listdir(root_folder)

    for item in all_items:
        item_path = os.path.join(root_folder, item)
        if os.path.isdir(item_path) and not item.startswith('.'):
            contents_dir = os.path.join(item_path, _NODES_FOLDER_NAME)
            if os.path.exists(contents_dir):
                projects.append(item)

    return projects

def create_project_id():
    now = datetime.datetime.now()
    random_digits = random.randint(1000, 9999)
    return now.strftime(f"TL_%Y_%m_%d_%H%M%S_{random_digits}")

def create_project(project_id: str=None):
    """
    创建写作项目。
    """
    project_id = project_id or create_project_id()

    return project_id

def is_content_exist(project_id: str, user_id: str="default_user"):
    """
    判断项目文件夹是否存在。
    """
    root_folder = get_textlong_folder()
    contents_dir = os.path.join(root_folder, user_id, project_id, _NODES_FOLDER_NAME)
    
    return os.path.exists(contents_dir)

def is_prompts_exist(project_id: str, user_id: str="default_user"):
    """
    判断项目文件夹是否存在。
    """
    root_folder = get_textlong_folder()
    prompt_dir = os.path.join(get_textlong_folder(), user_id, project_id, _PROMPTS_FOLDER_NAME)
    
    return os.path.exists(prompt_dir)

def load_content(project_id: str, id="0", user_id: str="default_user"):
    """
    从文件存储中，加载内容及其所有子节点。
    """
    root = None
    root_folder = get_textlong_folder()
    contents_dir = os.path.join(root_folder, user_id, project_id, _NODES_FOLDER_NAME)

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
                root = ContentNode(project_id=project_id, index=index, parent=None, **data)
            elif root:
                parent_id = '.'.join(id_parts[:-1]) if len(id_parts) > 1 else None
                parent = root.get_item_by_id(parent_id)

                # 写入子节点
                node = ContentNode(project_id=project_id, index=index, parent=parent, **data)
                parent._children[index] = node
            else:
                raise ValueError(f"根节点 {id} 还没有被创建")

    return root

def save_content(node: Union[ContentSerialize, "ContentTree", "WritingTask"], user_id: str="default_user"):
    """
    导出内容及其所有子节点，到文件存储。
    """
    if not node:
        print("⚠️ Nothing content to save !!")
        return False

    if type(node).__name__ == "NodeTree":
        node = node.root

    if type(node).__name__ == "WritingTask":
        node = node.tree.root
        
    if len(node.all_content) == 0:
        print("⚠️ Can't save when all_content is zero !!")
        return False

    root_folder = get_textlong_folder()

    # 保存内容节点
    for item in node.all_content:
        path = os.path.join(root_folder, user_id, node._project_id, _NODES_FOLDER_NAME, item['id']) + ".json"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(item, f, indent=4, ensure_ascii=False)
    
    return True

def load_prompts(node: Union[ContentSerialize, "ContentTree", "WritingTask"], id="0", user_id: str="default_user"):
    """
    为节点重新加载提示语模板。
    """
    if node == None:
        raise ValueError("⚠️ Nothing for prompts to load !!")

    if type(node).__name__ == "NodeTree":
        node = node.root

    if type(node).__name__ == "WritingTask":
        node = node.tree.root

    if node._project_id:
        for template_id in ["help", "init", "outline", "paragraph"]:
            prompt = load_chat_prompt(template_id, project_id=node._project_id, id=id, user_id=user_id)
            if prompt:
                setattr(node, f'{template_id}_prompt', prompt)
            else:
                return False
    
    return True

def save_prompts(node: Union[ContentSerialize, "ContentTree", "WritingTask"], id="0", user_id: str="default_user"):
    """
    保存提示语模板到项目目录。
    """
    if node == None:
        raise ValueError("⚠️ Nothing for prompts to save !!")

    if type(node).__name__ == "NodeTree":
        node = node.root

    if type(node).__name__ == "WritingTask":
        node = node.tree.root

    if node._project_id:
        save_chat_prompt(
            create_writing_help_prompt(),
            template_id='help',
            project_id=node._project_id,
            id=id,
            user_id=user_id,
        )

        save_chat_prompt(
            create_writing_init_prompt(),
            template_id='init',
            project_id=node._project_id,
            id=id,
            user_id=user_id,
        )

        save_chat_prompt(
            create_writing_todo_prompt(content_type='outline'),
            template_id='outline',
            project_id=node._project_id,
            id=id,
            user_id=user_id,
        )

        save_chat_prompt(
            create_writing_todo_prompt(content_type='paragraph'),
            template_id='paragraph',
            project_id=node._project_id,
            id=id,
            user_id=user_id,
        )
        
        return True

    return False

