from typing import Dict, Any

from .....utils import extract_segments, available_modules, raise_invalid_params
from .....io import EventBlock
from ..base import BaseAgent

import textwrap
import pandas as pd
import numpy as np

class PandasAgent(BaseAgent):
    """
    执行python代码的工具。
    """
    @classmethod
    def available_init_params(cls):
        return {
            "data": "数据集清单, 类型为 Dict[str, Dict[description: str, df: pd.DataFrame]]",
            "agent": "代码生成器",
            **BaseAgent.available_init_params(),
        }

    def __init__(self, data: Dict[str, Dict[description: str, df: pd.DataFrame]], agent: "ChatAgent", template_id: str=None, **kwargs):
        self.agent = agent
        self.data = data
        description = kwargs.pop("description", f"回答关于[{dataset_names}]等数据集的问题。\n具体包括：{self.dataset_desc()}")

        super().__init__(description=description, **kwargs)

        self._last_code = None

    @property
    def last_code(self):
        return self._last_code

    def call(self, question: str, *args, **kwargs):
        dataset_names = ', '.join(self.data.keys())
        dataset_desc = '\n - '.join([ds["description"] for ds in self.data.values()])

        output_text = ''
        for block in self.agent.call(question, *args, **kwargs):
            if block.block_type == 'chunk':
                output_text += block.text
            yield EventBlock("tool_resp_chunk", block.text)

        self._last_code = extract_segments(output_text, "```python", "```")
        if self.last_code:
            exec_result = self.execute_code(self.last_code)
            yield EventBlock("final_tool_resp", exec_result)
        else:
            yield EventBlock("warn", "没有正确生成python代码失败。")

    def dataset_desc(self):
        datasets = []
        if self.data:
            for ds_name, ds in self.data.items():
                head = ds["df"].head()
                example_md = head.to_markdown(index=False)
                datasets.append(textwrap.dedent(f"""
                ------------------------------
                **数据集名称：**
                {ds_name}
                
                **部份数据样例：**

                """) + example_md)

        return '\n'.join(datasets)

    def execute_code(self, code: str):
        """
        执行代码，并返回执行结果。
        """
        filtered_code = '\n'.join([line for line in code.split('\n') if not line.startswith('import')])

        # 受限的全局命名空间
        restricted_globals = {
            "__builtins__": {
                "print": print,
                "range": range,
                "len": len,
                "float": float,
                "int": int,
                "str": str,
                "set": set,
                "dict": dict,
                "list": list,
            },
            "data": self.data,  # 数据集清单
            "pd": pd  # 仅允许 pandas 模块
        }

        # 将附加代码添加到现有代码中
        filtered_code = f"{filtered_code}\n\nresult = main()\n"

        # 创建一个合并的命名空间
        exec_namespace = restricted_globals.copy()

        try:
            exec(filtered_code, exec_namespace)
        except Exception as e:
            return f"执行代码时发生错误: {e}"

        return exec_namespace.get('result', "生成的代码已经执行，但返回了空结果。")

