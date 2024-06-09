import os
import copy
from typing import Union, List, Dict, Any
from langchain.globals import set_verbose, get_verbose
from langchain_core.runnables import Runnable

from ..md import idea, rewrite, fetch, translate, outline, outline_self, outline_detail
from ..config import get_textlong_project
from ..parser import parse_markdown

class Command():
    def __init__(self, command: str, kwargs: Dict[str, Any], output: str):
        self.command = command
        self.kwargs = kwargs
        self.output = output

class Project():
    def __init__(self, project_folder: str=None, llm: Runnable=None):
        self.project_folder_name = project_folder
        self.llm = llm
        self.history: List[Command] = []
    
    @property
    def project_path(self):
        return self.get_filepath("")
    
    def get_filepath(self, filename):
        return get_textlong_project(filename, self.project_folder_name)
    
    def confirm_filepath(self, filename):
        path = self.get_filepath(filename)
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)

        return path

    def push_history(self, command: str, kwargs: Dict[str, Any], output: str):
        cmd = Command(command, kwargs, output)
        self.history.append(cmd)

    def save_markdown(self, filename: str, txt: str):
        """
        保存文本到文件。
        """

        if filename and txt:
            path = self.confirm_filepath(filename)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(txt)

    def load_markdown(self, filename: str=None):
        """
        从文件加载文本。
        """

        txt = None
        if filename:
            path = self.get_filepath(filename)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    txt = f.read()
        return txt

    def execute_task(self, task_func, task: str=None, output_file: str=None, prompt_id: str=None, input_file: str=None, input_doc: str=None, **kwargs):
        resp_md = ""
        _input_doc = input_doc or self.load_markdown(input_file)
        for x in task_func(
            llm=self.llm,
            prompt_id=prompt_id,
            input_doc=_input_doc,
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
 
        self.push_history(cmd_name, cmd_kwargs, resp_md)
        
        if output_file:
            self.save_markdown(output_file, resp_md)
        
    def valid_input(self, a, b):
        if a == None and b == None:
            raise ValueError("input doc or file MUST exist one!")

    def idea(self, task: str, output_file: str=None, **kwargs):
        self.execute_task(idea, task=task, output_file=output_file, **kwargs)

    def outline(self, task: str, output_file: str=None, **kwargs):
        self.execute_task(outline, task=task, output_file=output_file, **kwargs)

    def rewrite(self, input_file: str=None, output_file: str=None, input_doc: str=None, **kwargs):
        self.valid_input(input_file, input_doc)
        self.execute_task(rewrite, input_file=input_file, output_file=output_file, input_doc=input_doc, **kwargs)

    def fetch(self, input_file: str=None, output_file: str=None, input_doc: str=None, **kwargs):
        self.valid_input(input_file, input_doc)
        self.execute_task(fetch, input_file=input_file, output_file=output_file, input_doc=input_doc, **kwargs)

    def translate(self, input_file: str=None, output_file: str=None, input_doc: str=None, **kwargs):
        self.valid_input(input_file, input_doc)
        self.execute_task(translate, input_file=input_file, output_file=output_file, input_doc=input_doc, **kwargs)

    def outline_detail(self, input_file: str=None, output_file: str=None, input_doc: str=None, **kwargs):
        self.valid_input(input_file, input_doc)
        self.execute_task(outline_detail, input_file=input_file, output_file=output_file, input_doc=input_doc, **kwargs)

    def outline_self(self, input_file: str=None, output_file: str=None, input_doc: str=None, **kwargs):
        self.valid_input(input_file, input_doc)
        self.execute_task(outline_self, input_file=input_file, output_file=output_file, input_doc=input_doc, **kwargs)
