from typing import List, Dict, Any, Callable

from .....utils import raise_invalid_params
from .....io import EventBlock
from ....dataset import Dataset
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from ..chat import ChatAgent

import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import platform
import matplotlib.font_manager as fm

class PythonAgent(BaseAgent):
    """
    处理 Python 相关任务的基础 Agent。
    """
    @classmethod
    def allowed_params(cls):
        return {
            "agent": "生成代码的 ChatAgent 实例",
            "datasets": "数据集清单, 类型为 Dataset 实例，或者提供 `{name: Dataset}` 的键值对来创建 Dataset 实例",
            "exec_code": "是否执行生成的代码，默认为 True",
            "font_path": "字体路径，用于绘制图表时使用",
            **BaseAgent.allowed_params(),
        }

    def __init__(
        self,
        agent: ChatAgent,
        datasets: List[Dataset]=None,
        exec_code: bool=True,
        font_path: str=None,
        allow_vars: Dict[str, Any]=None,
        allow_safe_builtins: Dict[str, Callable]=None,
        allow_safe_header_code: List[str]=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.allowed_params())
        super().__init__(**kwargs)

        self.datasets = self._initialize_datasets(datasets)
        self.exec_code = exec_code
        self.allow_vars = allow_vars
        self.allow_safe_builtins = allow_safe_builtins
        self.allow_safe_header_code = allow_safe_header_code

        if not isinstance(agent, ChatAgent):
            raise ValueError("agent 必须是 ChatAgent 实例")

        self.agent = agent
        self.agent.fetching_output = ("```python", "```")

        self._last_code = None

        self.reset_datasets()

    def _initialize_datasets(self, datasets):
        if datasets:
            if isinstance(datasets, dict):
                if not all(isinstance(ds, Dataset) for ds in datasets.values()):
                    raise ValueError("datasets 每个值都必须是 `Dataset` 类型")
                return datasets
            elif isinstance(datasets, list):
                if not all(isinstance(ds, Dataset) for ds in datasets):
                    raise ValueError("datasets 每个值都必须是 `Dataset` 类型")
                return {ds.name: ds for ds in datasets}
            else:
                raise ValueError("datasets 必须是 `Dataset` 实例的列表")
        return {}

    def reset_datasets(self):
        """
        重置数据集描述
        """
        self.agent.reset_init_memory(self.prompt_template)
        self.description = self.datasets_description

    def add_dataset(self, df: pd.DataFrame, name: str, desc: str=None):
        """
        添加数据集
        """
        self.datasets[name] = Dataset(df, name, desc or name)

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
                "dataset_summary": lambda: self.datasets_summary,
                "safe_header_code": lambda: self.safe_header_code,
            })

    @property
    def last_code(self):
        """
        上一次生成的代码
        """
        return self._last_code

    def exec(self, code: str):
        """
        执行代码，并返回执行结果。
        """
        # 创建一个新的无污染空间
        exec_namespace = self.registered_global.copy()
        try:
            exec(code, exec_namespace)
        except Exception as e:
            return f"执行代码时发生错误: {e}"

        # 优先提取 result 变量的值
        last_output = exec_namespace.get('result')

        # 如果 result 不存在，则提取最后一个变量的值
        if last_output is None and exec_namespace:
            last_output = list(exec_namespace.values())[-1]

        # 显式删除 exec_namespace
        del exec_namespace

        # 返回提取的结果
        return last_output if last_output is not None else "生成的代码已经执行，但返回了空结果。"

    @property
    def registered_global(self):
        """
        注册全局变量
        """
        return {
            "__builtins__": self.safe_builtins,
            "last_output": None,
            "datasets": self.datasets,  # 数据集清单
            "add_dataset": self.add_dataset,  # 添加数据集
            "main": lambda: None,  # 默认的 main 函数
            **(self.allow_vars or {}),
        }

    @property
    def safe_header_code(self):
        """
        安全模块
        """
        return "\n".join([
            "import pandas as pd",
            "import numpy as np",
            "import seaborn as sns",
            "import matplotlib.pyplot as plt",
            "import matplotlib.font_manager as fm",
            *self.get_set_chinese_font_code(),
            *(self.allow_safe_header_code or []),
        ])

    def get_set_chinese_font_code(self):
        """
        根据操作系统返回设置中文字体的代码。
        """
        os_name = platform.system()
        if os_name == 'Darwin':  # macOS
            font_path = '/System/Library/Fonts/STHeiti Light.ttc'
        elif os_name == 'Windows':  # Windows
            font_path = 'C:/Windows/Fonts/simsun.ttc'
        elif os_name == 'Linux':  # Linux
            font_path = '/usr/share/fonts/truetype/arphic/ukai.ttc'
        else:
            raise RuntimeError("Unsupported operating system for setting Chinese font.")

        return [
            "# 设置中文字体",
            f"font_prop = fm.FontProperties(fname='{font_path}')",
            "plt.rcParams['font.family'] = font_prop.get_name()",
        ]

    @property
    def safe_builtins(self):
        """
        安全内置函数
        """
        return {
            "__import__": __import__,
            "abs": abs,
            "all": all,
            "any": any,
            "bin": bin,
            "bool": bool,
            "chr": chr,
            "str": str,
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
            "format": format,
            "frozenset": frozenset,
            "slice": slice,
            "type": type,
            "zip": zip,
            "classmethod": classmethod,
            "staticmethod": staticmethod,
            "property": property,
            "super": super,
            "issubclass": issubclass,
            "isinstance": isinstance,
            "iter": iter,
            "next": next,
            **(self.allow_safe_builtins or {}),
        }

    def call(self, question: str, **kwargs):
        self._last_output = ""
        self._last_code = ""

        new_chat = kwargs.pop("new_chat", True)
        self.agent.reset_init_memory(self.prompt_template)
        yield from self.agent.call(question, **kwargs, new_chat=new_chat)

        # 禁止代码中执行引入其他库的操作
        safety_code = '\n'.join([
            line
            for line
            in self.agent.last_output.split('\n')
            if not line.strip().startswith('import')
        ])
        self._last_code = "\n\n".join([
            self.safe_header_code,
            safety_code,
            "result = main()",
        ])

        try:
            if self.exec_code:
                if self.last_code:
                    result = self.exec(self.last_code)
                    if isinstance(result, pd.DataFrame):
                        self._last_output = result.to_markdown()
                    else:
                        self._last_output = str(result)
                    yield self.create_event_block("text", self._last_output)
                else:
                    yield self.create_event_block("warn", "没有正确生成python代码, 执行失败。")
            else:
                self._last_output = self.agent.last_output
        except Exception as e:
            self._last_output = str(e)
            yield self.create_event_block("text", self._last_output)
