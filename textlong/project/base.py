import os
import yaml
import copy
from datetime import datetime
from typing import Union, List, Dict, Any
from langchain.globals import set_verbose, get_verbose
from langchain_core.runnables import Runnable

from ..writing import from_idea, from_chunk, from_outline, extract, MarkdownDocuments
from ..config import (
    get_textlong_folder,
    get_default_public,
    get_default_project_config,
    get_default_project_script,
    get_default_project_logs,
)
from ..parser import parse_markdown
from ..exporter import export_jupyter
from ..importer import load_markdown
from ..utils import raise_not_supply_all

class Command():
    """
    长文生成指令。
    """
    def __init__(self, command: str, args: Dict[str, Any], output_text: str, modified_at: str=None):
        self.command = command
        self.args = {k: v for k, v in args.items() if v}
        self.output_text = output_text
        self.modified_at = modified_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def __str__(self):
        return "\n".join([
            self.__repr__()
        ])

    def __repr__(self):
        info = "".join([
            f'({self.modified_at})',
            self.command,
            f': {self.output_text[:10]}...' if len(self.output_text) > 10 else self.output_text[:10]
        ])
        return f"Command<{info}>"

    def to_dict(self):
        return {
            'command': self.command,
            'args': self.args,
            'modified_at': self.modified_at,
            'output_text': self.output_text,
        }
    
    def to_metadata(self):
        return {
            'command': self.command,
            'reference': {k: v for k, v in self.args.items() if v and k in ['prompt_id', 'input_file', 'kg_files']},
            'modified_at': self.modified_at,
        }

    @classmethod
    def from_dict(cls, dict_):
        return cls(**dict_)

class Project():
    """
    长文生成项目的文件管理。

    - {project_folder}
    - <textlong_folder>/{user_id}/{project_id}
    - <textlong_folder>/{user_id}/{project_id}/{file_path}
    """
    def __init__(self, llm: Runnable=None, project_folder: str=None, project_id: str=None, user_id: str=None):
        raise_not_supply_all("Project对象至少提供project_folder或project_id", project_folder, project_id)

        self.llm = llm
        self.project_folder = project_folder
        self.user_id = user_id or get_default_public()
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
        project_folder = self.project_folder or os.path.join('PROJECT_BASE', self.user_id, self.project_id)
        return f"Project<llm: '{self.llm._llm_type}/{self.llm.model}', project_folder: '{project_folder}', output_files: {self.output_files}>"

    def to_dict(self):
        return {attr: getattr(self, attr) for attr in vars(self) if attr != 'llm' and getattr(self, attr)}
    
    @property
    def project_config_path(self):
        return self.get_path(get_default_project_config())

    @property
    def project_script_path(self):
        return self.get_path(get_default_project_script())

    def _confirm_filepath(self, path):
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)

        return path

    def save_markdown(self, filepath: str, txt: str):
        """
        保存文本到markdown文件。
        """
        if filepath and txt:
            self._confirm_filepath(filepath)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(txt)

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
            yaml.safe_dump(self.to_dict(), f, allow_unicode=True)
        return True
    
    def _get_output_history_path(self, output_file):
        return self.get_path(get_default_project_logs(), output_file) + ".yml"
    
    def load_history(self, output_file):
        """
        查看命令生成历史。
        """
        path = self._get_output_history_path(output_file)
        return self._load_output_history(path)

    def load_commands(self):
        """
        加载所有命令。
        """
        commands = []
        for output_file in self.output_files:
            hist = self.load_history(output_file)
            commands.extend([{'cmd': cmd['command'], 'kwargs':cmd['args'],  'modified_at': cmd['modified_at']} for cmd in hist])
        if commands:
            commands = sorted(commands, key=lambda cmd: cmd['modified_at'])
        return commands

    def load_script(self):
        """
        加载执行脚本。
        """
        commands = []
        if os.path.exists(self.project_script_path):
            with open(self.project_script_path, 'r') as f:
                commands = yaml.safe_load(f) or []
        return commands

    def save_script(self):
        """
        保存命令执行的脚本，可用于批量自动执行。
        """
        os.makedirs(os.path.dirname(self.project_script_path), exist_ok=True)
        with open(self.project_script_path, 'w') as f:
            yaml.safe_dump(self.load_commands(), f, allow_unicode=True)
        return True
    
    def run_script(self):
        """
        自动执行脚本。
        """
        for cmd in self.load_script():
            if cmd['cmd'] == 'from_idea':
                self.from_idea(**cmd['kwargs'])
            elif cmd['cmd'] == 'from_outline':
                self.from_outline(**cmd['kwargs'])
            elif cmd['cmd'] == 'from_chunk':
                self.from_chunk(**cmd['kwargs'])
            elif cmd['cmd'] == 'extract':
                self.extract(**cmd['kwargs'])

    def _load_output_history(self, output_path):
        history = []
        if os.path.exists(output_path):
            with open(output_path, 'r') as f:
                history = yaml.safe_load(f) or []
        return history

    def save_output_history(self, output_file: str, command: Command):
        """
        保存生成历史。
        """
        path = self._get_output_history_path(output_file)
        history = self._load_output_history(path)

        history.append(command.to_dict())

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            yaml.safe_dump(history, f, allow_unicode=False)
 
    def get_path(self, *path):
        """
        获得基于项目文件夹的文件资源路径。
        """
        folder_path = self.project_folder or os.path.join(get_textlong_folder(), self.user_id, self.project_id)
        return os.path.join(folder_path, *path)
    
    def checkout(self, output_file: str, index: int=-2, save_as: str=None):
        """
        从历史记录中提取生成过的文本，默认提取倒数第2个。
        """
        history = self.load_history(output_file)
        output_text = history[index]['output_text']
        cmd = Command.from_dict(history[index])
        resp_md = MarkdownDocuments.to_front_matter(cmd.to_metadata()) + output_text
        self.save_markdown(self.get_path(save_as or output_file), resp_md)

    def export_jupyter(self, input_file: str, output_file: str):
        """
        导出为Jupyter笔记。
        """
        input_path = self.get_path(input_file)
        output_path = self.get_path(output_file)
        return export_jupyter(input_path, output_path)

    def _execute_task(self, task_func, output_file, task: str=None, prompt_id: str=None, input_file: str=None, kg_files: List[str]=None, **kwargs):
        command = task_func.__name__
        cmd_args = {
            "task": task,
            "input_file": input_file,
            "output_file": output_file,
            "kg_files": kg_files,
            "prompt_id": prompt_id,
            **kwargs
        }

        input_doc = None
        if input_file:
            docs = load_markdown(self.get_path(input_file))
            input_doc = docs.markdown

        knowledge = []
        if kg_files:
            if isinstance(kg_files, str):
                kg_files = [kg_files]
            for ref_file in kg_files:
                d = load_markdown(self.get_path(ref_file))
                knowledge.append(d.markdown)

        resp_md = ""
        for x in task_func(
            self.llm,
            prompt_id=prompt_id,
            input_doc=input_doc,
            knowledge=knowledge,
            task=task,
            **kwargs
        ):
            resp_md += x
            print(x, end="")

        cmd = Command(command, cmd_args, resp_md)

        # 保存生成结果
        resp_md = MarkdownDocuments.to_front_matter(cmd.to_metadata()) + resp_md
        self.save_markdown(self.get_path(output_file), resp_md)

        # 保存生成历史
        self.save_output_history(output_file, cmd)

        # 更新项目配置
        if output_file not in self.output_files:
            self.output_files.append(output_file)
            self.save_project()

    def from_idea(self, output_file: str, task: str, kg_files: List[str]=None, **kwargs):
        """
        从一个idea开始生成。
        """
        self._execute_task(from_idea, output_file=output_file, task=task, kg_files=kg_files, **kwargs)

    def from_outline(self, output_file: str, input_file: str, kg_files: List[str]=None, **kwargs):
        """
        从大纲开始扩写。
        """
        self._execute_task(from_outline, output_file=output_file, input_file=input_file, kg_files=kg_files, **kwargs)

    def from_chunk(self, output_file: str, input_file: str, kg_files: List[str]=None, **kwargs):
        """
        逐段重新生成。
        """
        self._execute_task(from_chunk, output_file=output_file, input_file=input_file, kg_files=kg_files, **kwargs)

    def extract(self, output_file: str, input_file: str, kg_files: List[str]=None, **kwargs):
        """
        整体提取。
        """
        self._execute_task(extract, output_file=output_file, input_file=input_file, kg_files=kg_files, **kwargs)
