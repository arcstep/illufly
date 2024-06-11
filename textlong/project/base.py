import os
import copy
from typing import Union, List, Dict, Any
from langchain.globals import set_verbose, get_verbose
from langchain_core.runnables import Runnable

from ..writing import from_idea, from_chunk, from_outline, extract
from ..config import get_textlong_project
from ..parser import parse_markdown
from ..exporter import export_jupyter, save_markdown
from ..importer import load_markdown

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
    
    def push_history(self, command: str, kwargs: Dict[str, Any], output: str):
        cmd = Command(command, kwargs, output)
        self.history.append(cmd)
    
    def export_jupyter(self, input_file, output_file):
        input_path = self.get_filepath(input_file)
        output_path = self.get_filepath(output_file)
        return export_jupyter(input_path, output_path)

    def execute_task(self, task_func, task: str=None, output_file: str=None, prompt_id: str=None, input_file: str=None, input_doc: str=None, **kwargs):
        """
        通用任务执行框架。
        """
        path = self.get_filepath(input_file)
        _input_doc = input_doc or load_markdown(path)

        resp_md = ""
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
            path = self.get_filepath(output_file)
            save_markdown(path, resp_md)
        
    def valid_not_none(self, a, b):
        if a == None and b == None:
            raise ValueError("input doc or file MUST exist one!")

    def from_idea(self, task: str, output_file: str=None, **kwargs):
        self.execute_task(from_idea, task=task, output_file=output_file, **kwargs)

    def from_outline(self, task: str, output_file: str=None, **kwargs):
        self.execute_task(from_outline, task=task, output_file=output_file, **kwargs)

    def from_chunk(self, input_file: str=None, output_file: str=None, input_doc: str=None, **kwargs):
        self.valid_not_none(input_file, input_doc)
        self.execute_task(from_chunk, input_file=input_file, output_file=output_file, input_doc=input_doc, **kwargs)

    def extract(self, input_file: str=None, output_file: str=None, input_doc: str=None, **kwargs):
        self.valid_not_none(input_file, input_doc)
        self.execute_task(extract, input_file=input_file, output_file=output_file, input_doc=input_doc, **kwargs)

