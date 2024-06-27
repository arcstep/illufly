import os
from langchain_core.runnables import Runnable
from .base import Project
from ..config import get_folder_public, get_folder_root, get_project_config_file

def is_project_existing(project_path):
    """递归检查项目目录中是否存在配置文件"""
    for root, dirs, files in os.walk(project_path):
        if get_project_config_file() in files:
            return True
    return False

def list_projects(base_folder: str=None):
    """列举项目"""
    base_folder = base_folder or get_folder_root()
    projects = []

    def walk_and_add_projects(folder):
        contains_config_file = False
        for root, dirs, files in os.walk(folder):
            if get_project_config_file() in files:
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
    return projects

def init_project(project_id: str, base_folder: str=None):
    """创建项目"""
    base_folder = base_folder or get_folder_root()
    p = Project(None, project_id=project_id)
    return p.save_project()
