import copy
from typing import Union, List
from langchain.globals import set_verbose, get_verbose

from ..md import idea, rewrite, fetch, translate, outline, outline_self, outline_detail
from ..config import get_textlong_project
from ..parser import parse_markdown

class Project():
    def __init__(self, project_folder: str=None):
        self.project_folder = get_textlong_project(project_folder)

