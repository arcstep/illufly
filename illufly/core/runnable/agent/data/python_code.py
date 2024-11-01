from typing import List, Dict

from .....utils import extract_segments, raise_invalid_params
from .....io import EventBlock
from ....dataset import Dataset
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from ..chat import ChatAgent

import textwrap
import pandas as pd
import numpy as np
import seaborn as sns

class PandasAgent(BaseAgent):
    """
    对所提供的 pandas 数据集做分析和处理。
    """
    @classmethod
    def allowed_params(cls):
        return {
            "datasets": "数据集清单, 类型为 Dataset 实例，或者提供 `{name: Dataset}` 的键值对来创建 Dataset 实例",
            "agent": "生成代码的 ChatAgent 实例",
            "template_id": "生成代码提示语模板ID",
            **BaseAgent.allowed_params(),
        }

    def __init__(self, agent: ChatAgent, datasets: List[Dataset]=None, template_id: str=None, **kwargs):
        raise_invalid_params(kwargs, self.allowed_params())

        if datasets:
            if isinstance(datasets, dict):
                if not all(isinstance(ds, Dataset) for ds in datasets.values()):
                    raise ValueError("datasets 每个值都必须是 `Dataset` 类型")
                self.datasets = datasets
            elif isinstance(datasets, list):
                if not all(isinstance(ds, Dataset) for ds in datasets):
                    raise ValueError("datasets 每个值都必须是 `Dataset` 类型")
                self.datasets = {ds.name: ds for ds in datasets}
            else:
                raise ValueError("datasets 必须是 `Dataset` 实例的列表")
        else:
            self.datasets = {}

        if not isinstance(agent, ChatAgent):
            raise ValueError("agent 必须是 ChatAgent 实例")

        self.template_id = template_id or "CODE/Pandas"

        self.agent = agent
        self.agent.start_marker = "```python"
        self.agent.end_marker = "```"

        self._last_code = None

        # 生成作为工具被使用时的功能描述
        _tool_params = kwargs.pop("tool_params", {
            "question": "细致描述数据分析任务的需求描述",
        })
        super().__init__(tool_params=_tool_params, **kwargs)
        self.reset_datasets()

    def reset_datasets(self):
        """
        重置数据集描述
        """
        self.agent.reset_init_memory(self.prompt_template)
        self.description = self.datasets_description

    @property
    def datasets_description(self):
        """
        数据集描述
        """
        names = ', '.join(self.datasets.keys())
        descs = '\n'.join([f"- {name}: {ds.desc}" for name, ds in self.datasets.items()])
        return f"回答关于[{names}]等数据集的相关问题。\n这些数据集具体包括：{descs}"

    @property
    def datasets_summary(self):
        """
        数据集摘要
        """
        return '\n'.join([ds.summary for ds in self.datasets.values()])

    @property
    def prompt_template(self):
        """
        提示语模板
        """
        return PromptTemplate(
            self.template_id,
            binding_map={
                "registered_global": lambda: list(self.registered_global.keys()),
                "safe_builtins": lambda: list(self.safe_builtins.keys()),
                "dataset_names": lambda: ', '.join(self.datasets.keys()),
                "dataset_description": lambda: self.datasets_description,
                "dataset_summary": lambda: self.datasets_summary
            })

    @property
    def safe_builtins(self):
        """
        安全内置函数
        """
        return {
            "abs": abs,
            "all": all,
            "any": any,
            "bin": bin,
            "bool": bool,
            "chr": chr,
            "complex": complex,
            "divmod": divmod,
            "enumerate": enumerate,
            "filter": filter,
            "hex": hex,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "iter": iter,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "next": next,
            "oct": oct,
            "ord": ord,
            "pow": pow,
            "range": range,
            "reversed": reversed,
            "round": round,
            "sorted": sorted,
            "sum": sum,
            "tuple": tuple,
            "dict": dict,
            "set": set,
            "frozenset": frozenset,
            "zip": zip,
            "hasattr": hasattr,
            "print": print,
    }

    def add_dataset(self, df: pd.DataFrame, name: str, desc: str=None):
        """
        添加数据集
        """
        self.datasets[name] = Dataset(df, name, desc or name)

    @property
    def registered_global(self):
        """
        注册全局变量
        """
        return {
            "__builtins__": self.safe_builtins,

            "last_output": None,
            "datasets": self.datasets, # 数据集清单
            "add_dataset": self.add_dataset, # 添加数据集

            "pd": pd,  # 允许 pandas 模块
            "np": np,  # 允许 numpy 模块
            "seaborn": sns, # 允许 seaborn 模块
            "sns": sns, # 允许 seaborn 模块

            "math": __import__('math'),
            "random": __import__('random'),
            "datetime": __import__('datetime'),
            "collections": __import__('collections'),
            "itertools": __import__('itertools'),
            "functools": __import__('functools'),
            "operator": __import__('operator'),
            "scipy": __import__('scipy'),
            "matplotlib": __import__('matplotlib'),
        }

    @property
    def last_code(self):
        """
        上一次生成的代码
        """
        return self._last_code

    def call(self, question: str, *args, **kwargs):
        new_chat = kwargs.pop("new_chat", True)
        self.agent.reset_init_memory(self.prompt_template)
        yield from self.agent.call(question, *args, **kwargs, new_chat=new_chat)

        self._last_code = self.agent.last_output
        if self.last_code:
            self._last_output = self.execute_code(self.last_code)
            yield EventBlock("text", self._last_output)
        else:
            yield EventBlock("warn", "没有正确生成python代码, 执行失败。")

    def execute_code(self, code: str):
        """
        执行代码，并返回执行结果。
        """

        # 禁止代码中执行引入其他库的操作
        safety_code = '\n'.join([line for line in code.split('\n') if not line.strip().startswith('import')])
        code_to_exec = f"{safety_code}\nlast_output = main()\n"

        # 创建一个新的无污染空间
        exec_namespace = self.registered_global.copy()
        try:
            exec(code_to_exec, exec_namespace)
        except Exception as e:
            return f"执行代码时发生错误: {e}"

        return exec_namespace.get('last_output', "生成的代码已经执行，但返回了空结果。")
