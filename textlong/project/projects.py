import os
from langchain_core.runnables import Runnable
from .base import Project
from ..config import get_default_public, get_textlong_folder, get_default_project_config

def list_projects(user_id: str=None):
    """列举项目"""
    path = os.path.join(get_textlong_folder(), user_id or get_default_public())
    return [
        name
        for name in os.listdir(path)
        if os.path.isdir(os.path.join(path, name)) and is_project_existing(name, user_id)
    ]

def create_project(project_id: str, user_id: str=None):
    """创建项目"""
    user_id = user_id or get_default_public()
    p = Project(project_id=project_id, user_id=user_id)
    return p.save_project()

def is_project_existing(project_id: str=None, user_id: str=None):
    path = os.path.join(
        get_textlong_folder(),
        user_id or get_default_public(),
        project_id,
        get_default_project_config()
    )
    return os.path.exists(path)
