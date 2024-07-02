import os
import yaml
from langchain_core.runnables import Runnable
from .base import BaseProject
from ..config import get_folder_root, get_env

def is_project_existing(project_path):
    """递归检查项目目录中是否存在配置文件"""
    for root, dirs, files in os.walk(project_path):
        if get_env("TEXTLONG_CONFIG_FILE") in files:
            return True
    return False

def list_projects(base_folder: str=None):
    """列举项目"""
    base_folder = base_folder or get_folder_root()

    project_list_file = os.path.join(base_folder, get_env("TEXTLONG_PROJECT_LIST"))
    if os.path.exists(project_list_file):
        with open(project_list_file, 'r') as f:
            return yaml.safe_load(f)
    
    projects = []

    def walk_and_add_projects(folder):
        contains_config_file = False
        for root, dirs, files in os.walk(folder):
            if get_env("TEXTLONG_CONFIG_FILE") in files:
                # 找到配置文件，标记此目录并停止遍历其子目录
                contains_config_file = True
                # 从 base_folder 到当前目录的相对路径
                relative_path = os.path.relpath(root, base_folder)
                projects.append(relative_path)
                break  # 停止当前目录的进一步遍历
            else:
                # 如果当前目录不包含配置文件，递归检查子目录
                for dir_name in dirs:
                    full_path = os.path.join(root, dir_name)
                    walk_and_add_projects(full_path)
            break  # 防止 os.walk 默认的递归行为

    walk_and_add_projects(base_folder)
    
    os.makedirs(os.path.dirname(project_list_file), exist_ok=True)
    with open(project_list_file, 'w') as f:
        yaml.safe_dump(projects, f, sort_keys=True, allow_unicode=True)

    return projects

def init_project(project_id: str, base_folder: str=None):
    """创建项目"""
    base_folder = base_folder or get_folder_root()
    p = BaseProject(project_id=project_id, base_folder=base_folder)
    return p.save_project()
