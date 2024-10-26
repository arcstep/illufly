from typing import Dict, Any

from .....utils import extract_segments, raise_invalid_params
from .....io import EventBlock
from ....dataset import Dataset
from ...prompt_template import PromptTemplate
from ..base import BaseAgent

import textwrap
import pandas as pd
import numpy as np

class PandasAgent(BaseAgent):
    """
    对所提供的 pandas 数据集做分析和处理。
    """
    @classmethod
    def available_init_params(cls):
        return {
            "datasets": "数据集清单, 类型为 Dataset 实例，或者提供 `{name: {description, df}}` 的键值对来创建 Dataset 实例",
            "agent": "生成代码的 ChatAgent 实例",
            "template_id": "生成代码提示语模板ID",
            **BaseAgent.available_init_params(),
        }

    def __init__(self, datasets: Dataset, agent: "ChatAgent", template_id: str=None, **kwargs):
        self.datasets = datasets if isinstance(datasets, Dataset) else Dataset(datasets)
        self.template_id = template_id or "CODE/Pandas"

        self.agent = agent
        template = PromptTemplate(self.template_id, binding_map={
            "registered_global": lambda: list(self.registered_global.keys()),
            "safe_builtins": lambda: list(self.safe_builtins.keys()),
            "names": lambda: self.datasets.names,
            "description": lambda: self.datasets.description,
            "summary": lambda: self.datasets.summary
        })
        self.agent.reset_init_memory(template)
        self.agent.start_marker = "```python"
        self.agent.end_marker = "```"

        # 生成作为工具被使用时的功能描述
        description = kwargs.pop(
            "description",
            f"回答关于[{self.datasets.names}]等数据集的问题。\n具体包括：{self.datasets.description}"
        )
        super().__init__(description=description, **kwargs)
        self._last_code = None
    @property
    def safe_builtins(self):
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
            "zip": zip,
    }

    @property
    def registered_global(self):
        return {
            "__builtins__": self.safe_builtins,
            "pd": pd,  # 允许 pandas 模块
            "np": np,  # 允许 numpy 模块
            "math": __import__('math'),
            "random": __import__('random'),
            "datetime": __import__('datetime'),
            "collections": __import__('collections'),
            "itertools": __import__('itertools'),
            "functools": __import__('functools'),
            "operator": __import__('operator'),
            "data": self.datasets.df,
            "pandas_code_exe_result": None,
        }

    @property
    def last_code(self):
        return self._last_code

    def call(self, question: str, *args, **kwargs):
        new_chat = kwargs.pop("new_chat", True)
        yield from self.agent.call(question, *args, **kwargs, new_chat=new_chat)

        self._last_code = self.agent.last_output
        if self.last_code:
            self._last_output = self.execute_code(self.last_code)
            yield EventBlock("text", self._last_output)
        else:
            yield EventBlock("warn", "没有正确生成python代码失败。")

    def execute_code(self, code: str):
        """
        执行代码，并返回执行结果。
        """

        # 禁止代码中执行引入其他库的操作
        safety_code = '\n'.join([line for line in code.split('\n') if not line.strip().startswith('import')])
        code_to_exec = f"{safety_code}\n\npandas_code_exe_result = main()\n"

        # 创建一个新的无污染空间
        exec_namespace = self.registered_global.copy()
        try:
            exec(code_to_exec, exec_namespace)
        except Exception as e:
            return f"执行代码时发生错误: {e}"

        return exec_namespace.get('pandas_code_exe_result', "生成的代码已经执行，但返回了空结果。")
