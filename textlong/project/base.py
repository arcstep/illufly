import os
import yaml
import copy
from datetime import datetime
from typing import Union, List, Dict, Any
from langchain.globals import set_verbose, get_verbose
from langchain_core.runnables import Runnable
from langchain_core.tracers.schemas import Run

from ..parser import parse_markdown, create_front_matter, fetch_front_matter
from ..exporter import export_jupyter
from ..importer import load_markdown
from ..utils import raise_not_supply_all
from ..config import (
    get_folder_root,
    get_folder_public,
    get_project_config_file,
    get_project_script_file,
    get_folder_logs,
)

from ..writing.command import Command
from ..writing import (
    MarkdownLoader,
    stream,
    write,
    idea,
    outline,
    from_outline,
    more_outline,
)

from ..writing.base import (
    get_idea_args,
    get_outline_args,
    get_from_outline_args,
    get_more_outline_args,
)

from ..chain import (
    create_qa_chain,
    create_chain,
    create_idea_chain,
    create_outline_chain,
    create_from_outline_chain,
    create_more_outline_chain,
)

def command_dependency(cmd1, cmd2):
    for value in cmd2['args'].values():
        if isinstance(value, str) and cmd1['output_file'] == value:
            return True
        elif isinstance(value, list) and cmd1['output_file'] in value:
            return True
    return False

def sort_commands(commands):
    sorted_commands = sorted(commands, key=lambda x: x['modified_at'])
    
    for i in range(len(sorted_commands)):
        for j in range(i + 1, len(sorted_commands)):
            if command_dependency(sorted_commands[j], sorted_commands[i]):
                sorted_commands[i], sorted_commands[j] = sorted_commands[j], sorted_commands[i]
    
    return sorted_commands

class Project():
    """
    长文生成项目的文件管理。
    
    - 写作指令: idea, outline, from_outline ...
    - 项目加载: load_project, save_project
    - 命令历史: load_commands, load_history
    - 项目脚本: save_script, load_script, run_script
    - 指令恢复: checkout
    """
    def __init__(self, llm: Runnable, project_id: str):
        raise_not_supply_all("Project 对象必须提供 llm", llm)
        raise_not_supply_all("Project 对象必须提供 project_id", project_id)

        self.llm = llm
        self.project_id = project_id
        self.output_files: List[str] = []

        if os.path.exists(self.project_config_path):
            data = self.load_project(self.project_config_path)
            if 'output_files' in data:
                self.output_files = data['output_files'] or []

    def __str__(self):
        return "\n".join([
            self.__repr__()
        ])

    def __repr__(self):
        return f"Project<llm: '{self.llm._llm_type}/{self.llm.model}', project_folder: '{self.project_folder}', output_files: {self.output_files}>"

    def to_dict(self):
        return {attr: getattr(self, attr) for attr in vars(self) if attr != 'llm' and getattr(self, attr)}
    
    @property
    def project_config_path(self):
        return self.get_path(get_project_config_file())

    @property
    def project_script_path(self):
        return self.get_path(get_project_script_file())

    @property
    def project_folder(self):
        return os.path.join(get_folder_root(), self.project_id)

    def save_markdown_as(self, filepath: str, txt: str):
        """
        保存文本到markdown文件。
        """
        md_text = txt
        if filepath and md_text:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(md_text)

        return True

    def load_project(self, config_path: str):
        """
        加载项目。
        """
        state = {}
        with open(config_path, 'r') as f:
            state = yaml.safe_load(f)
        return state

    def save_project(self):
        """
        保存项目。
        """
        os.makedirs(os.path.dirname(self.project_config_path), exist_ok=True)
        with open(self.project_config_path, 'w') as f:
            yaml.safe_dump(self.to_dict(), f, allow_unicode=True, sort_keys=False)
        return True

    def _get_output_history_path(self, output_file):
        return self.get_path(get_folder_logs(), output_file) + ".yml"
    
    def load_history(self, output_file, start: int=None, end: int=None):
        """
        查看命令生成历史。
        """
        path = self._get_output_history_path(output_file)
        return self._load_output_history(path)[start:end]

    def load_commands(self, start: int=None, end: int=None):
        """
        从日志加载所有命令。

        根据生成顺序的依赖关系排序: 如果指令对象的output_file出现在对方的args中就排在其钱买呢。
        """
        commands = []
        for output_file in self.output_files:
            commands.extend([
                {
                    'modified_at': cmd['modified_at'],
                    'output_file': cmd['output_file'],
                    'command': cmd['command'],
                    'args':cmd['args'],
                }
                for cmd in self.load_history(output_file, start, end)
            ])
        if commands:
            commands = sort_commands(commands)
        return commands

    def load_script(self, script_path: str=None):
        """
        加载执行脚本。
        """
        commands = []
        path = script_path or self.project_script_path
        if os.path.exists(path):
            with open(path, 'r') as f:
                commands = yaml.safe_load(f) or []
        return commands

    def save_script(self, script_path: str=None, start: int=-1, end: int=None):
        """
        保存命令执行的脚本，可用于批量自动执行。
        
        默认保存每个文件处理历史命令中的最后一个: [-1, None]。
        """
        path = script_path or self.project_script_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            yaml.safe_dump(self.load_commands(start, end), f, allow_unicode=True, sort_keys=False)
        return True
    
    def run_script(self, script_path: str=None):
        """
        自动执行脚本。
        """
        for cmd in self.load_script(script_path):
            if cmd['command'] in ['stream']:
                self.exec(write, output_file=cmd['output_file'], **cmd['args'])

    def _load_output_history(self, output_path):
        history = []
        if os.path.exists(output_path):
            with open(output_path, 'r') as f:
                history = yaml.safe_load(f) or []
        return history

    def _save_output_history(self, output_file: str, output_text: str):
        """
        保存生成历史。
        """
        hist_path = self._get_output_history_path(output_file)

        history = self._load_output_history(hist_path)
        front_matter, text = fetch_front_matter(output_text)
        front_matter['output_text'] = output_text
        command = Command.from_dict(front_matter)

        history.append(command.to_dict())

        os.makedirs(os.path.dirname(hist_path), exist_ok=True)
        with open(hist_path, 'w') as f:
            yaml.safe_dump(history, f, allow_unicode=False, sort_keys=False)
 
    def get_path(self, *path):
        """
        获得基于项目文件夹的文件资源路径。
        """
        return os.path.join(self.project_folder, *path)
    
    def checkout(self, output_file: str, index: int=-2, save_as: str=None):
        """
        从历史记录中提取生成过的文本，默认提取倒数第2个。
        """
        history = self.load_history(output_file)
        output_text = history[index]['output_text']
        cmd = Command.from_dict(history[index])
        resp_md = create_front_matter(cmd.to_metadata()) + output_text
        return self.save_markdown_as(self.get_path(save_as or output_file), resp_md)

    def export_jupyter(self, input_file: str, output_file: str):
        """
        导出为Jupyter笔记。
        """
        input_path = self.get_path(input_file)
        output_path = self.get_path(output_file)
        return export_jupyter(input_path, output_path)

    def exec(self, task_func, output_file: str=None, **kwargs):
        kwargs['base_folder'] = self.project_folder
        kwargs['output_file'] = output_file
        output_text = task_func(
            self.llm,
            **kwargs
        )

        self._save_output_history(output_file, output_text)

        if output_file not in self.output_files:
            self.output_files.append(output_file)
            self.save_project()

    def create_exec_chain(self, output_file: str, **kwargs):
        kwargs['base_folder'] = self.project_folder
        kwargs['output_file'] = output_file
        chain = create_chain(
            self.llm,
            stream,
            **kwargs
        )

        def fn_end(run_obj: Run):
            # print(run_obj)
            self._save_output_history(output_file, run_obj.outputs['output'])
            if output_file not in self.output_files:
                self.output_files.append(output_file)
                self.save_project()

        return chain.with_listeners(on_end=fn_end)

    def idea(self, output_file: str, task: str, **kwargs):
        """
        从一个idea开始生成。
        """
        self.exec(idea, output_file=output_file, task=task, **kwargs)

    def create_idea_chain(self, output_file: str, prompt_id: str=None, **kwargs):
        return self.create_exec_chain(output_file, **get_idea_args(prompt_id, **kwargs))
    
    def outline(self, output_file: str, task: str, **kwargs):
        """
        生成写作大纲。
        """
        self.exec(outline, output_file=output_file, task=task, **kwargs)

    def create_outline_chain(self, output_file: str, prompt_id: str=None, **kwargs):
        return self.create_exec_chain(output_file, **get_outline_args(prompt_id, **kwargs))

    def more_outline(self, output_file: str,  input: Union[str, list[str]], **kwargs):
        """
        从已有大纲获得更多大纲。
        """
        self.exec(more_outline, output_file=output_file, input=input **kwargs)

    def create_more_outline_chain(self, output_file: str, prompt_id: str=None, **kwargs):
        return self.create_exec_chain(output_file, **get_more_outline_args(prompt_id, **kwargs))

    def from_outline(self, output_file: str, input: Union[str, list[str]], **kwargs):
        """
        从大纲扩写。
        """
        self.exec(from_outline, output_file=output_file, input=input, **kwargs)

    def create_from_outline_chain(self, output_file: str, prompt_id: str=None, **kwargs):
        return self.create_exec_chain(output_file, **get_from_outline_args(prompt_id, **kwargs))
