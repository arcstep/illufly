import re
import os
import shutil
import yaml
import copy
import random
from datetime import datetime
from typing import Union, List, Dict, Any
from langchain.globals import set_verbose, get_verbose
from langchain_core.runnables import Runnable
from langchain_core.runnables.utils import Input, Output
from langchain_core.tracers.schemas import Run
from langchain.memory import ConversationBufferWindowMemory

from ..parser import parse_markdown, create_front_matter, fetch_front_matter
from ..exporter import export_jupyter
from ..importer import load_markdown
from ..utils import raise_not_supply_all, safety_path
from ..config import get_folder_root, get_env

from ..writing.command import Command
from ..writing import (
    MarkdownLoader,
    stream,
    stream_log,
    get_default_writing_args,

    chat,
    idea,
    outline,
    from_outline,
    more_outline,
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

class BaseProject():
    """
    基于项目管理写作文件。
    
    - 项目保存: save_project
    - 命令历史: load_commands, load_history
    - 项目脚本: save_script, load_script
    - 指令恢复: checkout
    """
    def __init__(self, project_id: str, base_folder: str=None, prompt_tag=None):
        raise_not_supply_all("Project 对象必须提供有效的 project_id", project_id)

        self.base_folder = base_folder or get_folder_root()
        self.project_id = safety_path(project_id)
        self.output_files: Set[str] = set()
        self.embedding_files: Set[str] = set()
        self.prompt_tag = prompt_tag

        if os.path.exists(self.project_config_path):
            data = self._load_project_data()
            if 'output_files' in data:
                self.output_files = set(data['output_files'] or [])
            if 'embedding_files' in data:
                self.embedding_files = set(data['embedding_files'] or [])

    def __str__(self):
        return "\n".join([
            self.__repr__()
        ])

    def __repr__(self):
        return f"Project<project_folder: '{self.project_folder}', output_files: {list(self.output_files)}>"

    def to_dict(self):
        return {
            "base_folder": self.base_folder,
            "project_id": self.project_id,
            "output_files": list(self.output_files),
            "embedding_files": list(self.embedding_files),
        }
    
    @property
    def project_config_path(self):
        return self.get_path(get_env("TEXTLONG_CONFIG_FILE"))

    @property
    def project_script_path(self):
        return self.get_path(get_env("TEXTLONG_SCRIPT_FILE"))

    @property
    def project_folder(self):
        return os.path.join(self.base_folder, self.project_id)
    
    def load_markdown(self, filepath: str):
        """
        加载markdown文件。
        """
        path = self.get_path(filepath)
        txt = ""
        if path:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    txt = f.read()        
        return txt

    def list_resource(self):
        """
        列举markdown文件清单，排除exclude_paths中任何元素开头或以"."开头的路径。
        """
        all_paths = []
        exclude_paths = [
            get_env("TEXTLONG_SCRIPT_FILE"),
            get_env("TEXTLONG_CONFIG_FILE"),
            get_env("TEXTLONG_LOGS"),
        ]
        for root, dirs, files in os.walk(self.project_folder):
            for name in files:
                file_path = os.path.join(root, name)
                relative_path = os.path.relpath(file_path, self.project_folder)
                if not any(relative_path.startswith(exclude) or relative_path.startswith('.') for exclude in exclude_paths):
                    all_paths.append(relative_path)
            for name in dirs:
                dir_path = os.path.join(root, name)
                relative_path = os.path.relpath(dir_path, self.project_folder)
                if not any(relative_path.startswith(exclude) or relative_path.startswith('.') for exclude in exclude_paths):
                    all_paths.append(relative_path)
        return all_paths

    def save_markdown_as(self, res_name: str, txt: str):
        """
        保存文本到markdown文件。
        """
        md_text = txt or "\n"
        path = self.get_path(res_name)
        if path and md_text:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(md_text)

        return path

    def to_output(self, res_name: str, as_output=True):
        """
        修改文件资源是否纳入到输出清单。
        """
        if as_output:
            self.output_files.add(res_name)
        else:
            self.output_files.discard(res_name)
        self.save_project()

        return self.output_files
    
    def to_embedding(self, res_name: str, as_embedding=True):
        """
        修改文件资源是否纳入到文本嵌入清单。
        """
        if as_embedding:
            self.embedding_files.add(res_name)
        else:
            self.embedding_files.discard(res_name)
        self.save_project()

        return self.embedding_files

    def _load_project_data(self):
        """
        加载项目。
        """
        state = {}
        with open(self.project_config_path, 'r') as f:
            state = yaml.safe_load(f)
        return state

    def save_project(self):
        """
        保存项目。
        """
        os.makedirs(os.path.dirname(self.project_config_path), exist_ok=True)
        with open(self.project_config_path, 'w') as f:
            yaml.safe_dump(self.to_dict(), f, allow_unicode=True, sort_keys=False)

        all_projects = []
        project_list_file = os.path.join(self.base_folder, get_env("TEXTLONG_PROJECT_LIST"))
        if os.path.exists(project_list_file):
            with open(project_list_file, 'r') as f:
                all_projects = yaml.safe_load(f)
        
        if self.project_id not in all_projects:
            all_projects.append(self.project_id)
            with open(project_list_file, 'w') as f:
                yaml.safe_dump(all_projects, f, sort_keys=True, allow_unicode=True)

        return True

    def _get_output_history_path(self, output_file, version=""):
        output_file = safety_path(output_file)
        return self.get_path(get_env("TEXTLONG_LOGS"), version, output_file) + ".yml"
    
    def load_history(self, output_file, start: int=None, end: int=None, version=""):
        """
        查看命令生成历史。

        支持按照按版本管理日志历史。
        """
        path = self._get_output_history_path(output_file, version)
        return self._load_output_history(path)[start:end]

    def clear_history(self, output_file: str=None, version: str=None):
        """
        查看命令生成历史。

        支持按照按版本管理日志历史。
        """
        output_file = output_file or get_env("TEXTLONG_DEFAULT_OUTPUT")
        now_path = self._get_output_history_path(output_file, "")

        version = version or next(create_ver_id())
        ver_path = self._get_output_history_path(output_file, version)
        os.makedirs(os.path.dirname(ver_path), exist_ok=True)

        # 检查ver_path指向的文件是否存在
        if os.path.exists(now_path):
            shutil.move(now_path, ver_path)
            with open(now_path, 'w') as file:
                file.truncate()
                if output_file in self.memory:
                    self.memory.pop(output_file)
                return f'Clear succeed: {output_file}'

        return f'Clear failed: {output_file}'

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
        script_path = safety_path(script_path)
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
        script_path = safety_path(script_path)
        path = script_path or self.project_script_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            yaml.safe_dump(self.load_commands(start, end), f, allow_unicode=True, sort_keys=False)
        return True
    
    def _load_output_history(self, output_path):
        history = []
        if os.path.exists(output_path):
            with open(output_path, 'r') as f:
                history = yaml.safe_load(f) or []
        return history

    def save_output_history(self, output_file: str, output_text: str):
        """
        保存生成历史。
        """
        hist_path = self._get_output_history_path(output_file)

        history = self._load_output_history(hist_path)
        front_matter, text = fetch_front_matter(output_text)
        front_matter['output_text'] = text
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

    def checkout(self, to_output: str=None, from_output: str=None, ver_index: int=None):
        """
        从历史版本中提取。

        - 默认版本提取规则：如果提供新文件名 to_output 就从当前版本中提取，否则从上一版本中提取
        """
        if ver_index == None:
            ver_index = -1 if to_output else -2
        from_output =  safety_path(from_output or get_env("TEXTLONG_DEFAULT_OUTPUT"))
        to_output = safety_path(to_output or from_output)
        history = self.load_history(from_output)
        output_text = history[ver_index]['output_text']
        cmd = Command.from_dict(history[ver_index])
        resp_md = create_front_matter(cmd.to_metadata()) + output_text
        return self.save_markdown_as(to_output, resp_md)

    def export_jupyter(self, input_file: str, output_file: str):
        """
        导出为Jupyter笔记。
        """
        input_path = self.get_path(input_file)
        output_path = self.get_path(output_file)
        return export_jupyter(input_path, output_path)

class WritingProject(BaseProject):
    """
    在 Project 中管理写作任务。

    - 写作指令: chat, outline, from_outline ...
    - 项目脚本: run_script
    """
    def __init__(self, llm: Runnable=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm = llm
        self.memory = {}

    def __repr__(self):
        return f"Project<llm: '{self.llm._llm_type}/{self.llm.model}', project_folder: '{self.project_folder}', output_files: {list(self.output_files)}>"

    def get_memory(self, output_file: str):
        """
        获得文件的历史记忆。
        """
        if output_file not in self.memory:
            self.memory[output_file] = ConversationBufferWindowMemory()

            if output_file in self.output_files:
                hist = self.load_history(output_file)
                for cmd in hist:
                    args = cmd['args']
                    task = cmd['args'].get("task", "") if args else ''
                    output_text = cmd['output_text']
                    self.memory[output_file].save_context({'input': task}, {'output': output_text})

        return self.memory[output_file]

    def run_script(self, script_path: str=None):
        """
        自动执行脚本。
        """
        for cmd in self.load_script(script_path):
            if cmd['command'] in ['stream']:
                self.stream_log(stream_log, output_file=cmd['output_file'], **cmd['args'])

    def stream_log(self, task_func, output_file: str=None, **kwargs):
        """
        基于Project内封装的状态执行写作任务。
        
        借助该函数对 llm / prompt_tag / base_folder 等封装可以实现平行输出，以便对生成质量做评估。

        Args:
        - llm 直接采纳 self.llm
        - base_folder 直接采纳 self.project_folder
        - prompt_tag 如果执行参数没有提供，就采纳 self.prompt_tag
        """
        output_file = output_file or get_env("TEXTLONG_DEFAULT_OUTPUT")
        kwargs['base_folder'] = self.project_folder
        kwargs['output_file'] = output_file
        kwargs['prompt_tag'] = kwargs.get('prompt_tag', self.prompt_tag)
        kwargs['memory'] = self.get_memory(output_file)
        output_text = task_func(
            self.llm,
            **kwargs
        )

        self.save_output_history(output_file, output_text)

        if output_file and output_file not in self.output_files:
            self.output_files.add(output_file)
            self.save_project()

    def chat(self, task: str, output_file: str=None, **kwargs):
        """
        对话。
        """
        self.stream_log(chat, task=task, output_file=output_file, memory=self.memory, **kwargs)

    def idea(self, task: str, output_file: str=None, **kwargs):
        """
        从一个idea开始生成。
        """
        self.stream_log(idea, task=task, output_file=output_file, **kwargs)

    def outline(self, task: str, output_file: str=None, **kwargs):
        """
        生成写作大纲。
        """
        self.stream_log(outline, output_file=output_file, task=task, **kwargs)

    def more_outline(self, completed: Union[str, list[str]], output_file: str=None, **kwargs):
        """
        从已有大纲获得更多大纲。
        """
        self.stream_log(more_outline, output_file=output_file, completed=completed, **kwargs)

    def from_outline(self, completed: Union[str, list[str]], output_file: str=None, **kwargs):
        """
        从大纲扩写。
        """
        self.stream_log(from_outline, output_file=output_file, completed=completed, **kwargs)

def create_ver_id():
    counter = 0
    while True:
        date_str = datetime.now().strftime("%y%m%d")
        random_number = f'{random.randint(0, 99):02}'
        counter_str = f'{counter:02}'
        yield f'{date_str}{random_number}{counter_str}'
        counter = 0 if counter == 99 else counter + 1
