import os
import copy
from typing import Union, List
from langchain.globals import set_verbose, get_verbose
from langchain_core.runnables import Runnable

from ..md import idea, rewrite, fetch, translate, outline, outline_self, outline_detail
from ..config import get_textlong_project
from ..parser import parse_markdown

class Project():
    def __init__(self, project_folder: str=None, llm: Runnable=None):
        self.project_folder_name = project_folder
        self.llm = llm
    
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

    def save(self, filename: str, txt: str):
        """
        保存文本到文件。
        """

        if filename and txt:
            path = self.confirm_filepath(filename)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(txt)

    def load(self, filename: str=None):
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
    
    def idea(self, task: str, output_file: str=None, template_id: str=None, input_file: str=None, input_doc: str=None, **kwargs):
        resp_md = ""
        for x in idea(
            task=task,
            llm=self.llm,
            template_id=template_id,
            input_doc=self.load(input_file, input_doc),
            **kwargs
        ):
            resp_md += x
            print(x, end="")
        
        if output_file:
            self.save(output_file, resp_md)

    def outline(self, task: str, output_file: str=None, template_id: str=None, input_file: str=None, input_doc: str=None, **kwargs):
        resp_md = ""
        for x in outline(
            task=task,
            llm=self.llm,
            template_id=template_id,
            input_doc=self.load(input_file, input_doc),
            **kwargs
        ):
            resp_md += x
            print(x, end="")

        if output_file:
            self.save(output_file, resp_md)

    def rewrite(self, input_doc: str=None, output_file: str=None, template_id: str=None, task: str=None, input_file: str=None, **kwargs):
        resp_md = ""
        _input_doc = input_doc or self.load(input_file)
        for x in rewrite(
            task=task,
            llm=self.llm,
            template_id=template_id,
            input_doc=_input_doc,
            **kwargs
        ):
            resp_md += x
            print(x, end="")
        
        if output_file:
            self.save(output_file, resp_md)

    def fetch(self, input_doc: str=None, output_file: str=None, template_id: str=None, task: str=None, input_file: str=None, **kwargs):
        resp_md = ""
        _input_doc = input_doc or self.load(input_file)
        for x in fetch(
            task=task,
            llm=self.llm,
            template_id=template_id,
            input_doc=_input_doc,
            **kwargs
        ):
            resp_md += x
            print(x, end="")
        
        if output_file:
            self.save(output_file, resp_md)

    def translate(self, input_doc: str=None, output_file: str=None, template_id: str=None, task: str=None, input_file: str=None, **kwargs):
        resp_md = ""
        _input_doc = input_doc or self.load(input_file)
        for x in translate(
            task=task,
            llm=self.llm,
            template_id=template_id,
            input_doc=_input_doc,
            **kwargs
        ):
            resp_md += x
            print(x, end="")
        
        if output_file:
            self.save(output_file, resp_md)

    def outline_detail(self, input_doc: str=None, output_file: str=None, template_id: str=None, task: str=None, input_file: str=None, **kwargs):
        resp_md = ""
        _input_doc = input_doc or self.load(input_file)
        for x in outline_detail(
            task=task,
            llm=self.llm,
            template_id=template_id,
            input_doc=_input_doc,
            **kwargs
        ):
            resp_md += x
            print(x, end="")
        
        if output_file:
            self.save(output_file, resp_md)

    def outline_self(self, input_doc: str=None, output_file: str=None, template_id: str=None, task: str=None, input_file: str=None, **kwargs):
        resp_md = ""
        _input_doc = input_doc or self.load(input_file)
        for x in outline_self(
            task=task,
            llm=self.llm,
            template_id=template_id,
            input_doc=_input_doc,
            **kwargs
        ):
            resp_md += x
            print(x, end="")
        
        if output_file:
            self.save(output_file, resp_md)
