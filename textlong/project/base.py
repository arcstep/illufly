import os
import copy
from datetime import datetime
from typing import Union, List, Dict, Any
from langchain.globals import set_verbose, get_verbose
from langchain_core.runnables import Runnable

from ..writing import from_idea, from_chunk, from_outline, extract
from ..config import get_textlong_folder, get_default_public
from ..parser import parse_markdown
from ..exporter import export_jupyter, save_markdown
from ..importer import load_markdown
from ..utils import raise_not_supply_all

class Command():
    """
    长文生成指令。
    """
    def __init__(self, cmd_name: str, cmd_kwargs: Dict[str, Any], output_text: str):
        self.cmd_name = cmd_name
        self.cmd_kwargs = cmd_kwargs
        self.output_text = output_text
        self.modified_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

class History():
    """
    指令历史。
    """
    def __init__(self):
        self.commands: List[Command] = []
    
    def append(self, cmd: Command):
        self.commands.append(cmd)
    
    def __str__(self):
        return "\n".join([
            self.__repr__()
        ])

    def __repr__(self):
        cmds = ", ".join([f'{cmd.cmd_name}' for cmd in self.history])
        return f"History<commands: [{cmds}]"

class Project():
    """
    本地项目管理。

    - {project_folder}
    - <textlong_folder>/{user_id}/{project_id}
    - <textlong_folder>/{user_id}/{project_id}/{file_path}
    """
    def __init__(self, llm: Runnable=None, project_folder: str=None, project_id: str=None, user_id: str=None, title: str=None):
        raise_not_supply_all("Project对象至少提供project_folder或project_id", project_folder, project_id)

        self.title = title
        self.llm = llm
        self.project_folder = project_folder
        self.user_id = user_id or get_default_public()
        self.project_id = project_id
        self.output_files: Dict[str, History] = {}

    def __str__(self):
        return "\n".join([
            self.__repr__()
        ])

    def __repr__(self):
        project_folder = self.project_folder or os.path.join('PROJECT_BASE', self.user_id, self.project_id)
        return f"Project<llm: {self.llm._llm_type}/{self.llm.model}, project_folder: {project_folder}, title: {self.title}>"

    @property
    def project_path(self):
        return self.get_filepath("")

    def get_filepath(self, filename):
        folder_path = self.project_folder or os.path.join(get_textlong_folder(), self.user_id, self.project_id)
        return os.path.join(folder_path, filename)

    def push_history(self, output_file: str, cmd_name: str, cmd_kwargs: Dict[str, Any], output_text: str):
        cmd = Command(cmd_name, cmd_kwargs, output_text)
        if output_file in self.output_files:
            history = self.output_files[output_file]
        else:
            history = History()
            self.output_files[output_file] = history
        history.append(cmd)

    def export_jupyter(self, input_file, output_file):
        input_path = self.get_filepath(input_file)
        output_path = self.get_filepath(output_file)
        return export_jupyter(input_path, output_path)

    def execute_task(self, task_func, output_file, task: str=None, prompt_id: str=None, input_file: str=None, input_doc: str=None, **kwargs):
        """
        通用任务执行框架。
        """
        if input_file:
            input_doc = load_markdown(self.get_filepath(input_file))

        resp_md = ""
        for x in task_func(
            self.llm,
            prompt_id=prompt_id,
            input_doc=input_doc,
            task=task,
            **kwargs
        ):
            resp_md += x
            print(x, end="")
        
        cmd_name = task_func.__name__
        cmd_kwargs = {
            "task": task,
            "output_file": output_file,
            "prompt_id": prompt_id,
            "input_file": input_file,
            "input_doc": input_doc,
            **kwargs
        }
 
        self.push_history(output_file, cmd_name, cmd_kwargs, resp_md)

        if output_file:
            path = self.get_filepath(output_file)
            save_markdown(path, resp_md)

    def from_idea(self, output_file: str, task: str, **kwargs):
        self.execute_task(from_idea, output_file=output_file, task=task, **kwargs)

    def from_outline(self, output_file: str, task: str, **kwargs):
        self.execute_task(from_outline, output_file=output_file, task=task, **kwargs)

    def from_chunk(self, output_file: str, input_file: str=None, input_doc: str=None, **kwargs):
        raise_not_supply_all("from_chunk至少提供input_file或input_doc", input_file, input_doc)
        self.execute_task(from_chunk, output_file=output_file, input_file=input_file, input_doc=input_doc, **kwargs)

    def extract(self, output_file: str, input_file: str=None, input_doc: str=None, **kwargs):
        raise_not_supply_all("extract至少提供input_file或input_doc", input_file, input_doc)
        self.execute_task(extract, output_file=output_file, input_file=input_file, input_doc=input_doc, **kwargs)

