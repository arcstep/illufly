import os
from langchain_core.runnables import Runnable
from .base import Project
from ..config import get_folder_public, get_folder_root, get_project_config_file

def list_projects(base_folder: str=None):
    """列举项目"""
    path = os.path.join(get_folder_root(), base_folder or get_folder_public())
    print(path)
    all = os.listdir(path)
    if all:
        return [
            name
            for name in all
            if os.path.isdir(os.path.join(path, name)) and is_project_existing(name, base_folder)
        ]
    else:
        return []

def init_project(project_id: str, base_folder: str=None):
    """创建项目"""
    base_folder = base_folder or get_folder_public()
    p = Project(project_id=project_id, base_folder=base_folder)
    return p.save_project()

def is_project_existing(project_id: str=None, base_folder: str=None):
    path = os.path.join(
        get_folder_root(),
        base_folder or get_folder_public(),
        project_id,
        get_project_config_file()
    )
    return os.path.exists(path)
