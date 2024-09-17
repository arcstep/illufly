from typing import Dict, Any

from ..hub import load_template
from ..io import TextBlock
from ..core.agent import BaseAgent, BaseTool
from ..core.template import Template

import textwrap
import pandas as pd
import numpy as np

def parse_code(code: str):
    """
    解析代码，去除代码块的标记。
    """
    return code.replace("```python", "").replace("```", "")

def execute_code(data: Dict[str, Any], code: str):
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
        "data": data,  # 数据集清单
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

class PythonCodeTool(BaseAgent):
    def __init__(self, data: Dict[str, "Dataset"], agent: "ChatAgent", name: str=None, description: str=None, template_id: str=None, **kwargs):
        super().__init__(func=self.python_code, **kwargs)

        self.gen_code_agent = agent

        self.data = data

        self.name = name or "python_code"
        self.description = description or f"回答关于[{dataset_names}]等数据集的问题。\n具体包括：{BaseTool.dataset_desc(self.data)}"

    def call(self, question: str, *args, **kwargs):
        dataset_names = ', '.join(self.data.keys())
        dataset_desc = '\n - '.join([ds.desc for ds in self.data.values()])

        output_text = ''
        for block in self.gen_code_agent.call(question, *args, **kwargs):
            if block.block_type == 'chunk':
                output_text += block.text
            yield TextBlock("tool_resp_chunk", block.text)

        code = parse_code(output_text)
        if code:
            exec_result = execute_code(self.data, code)
            yield TextBlock("tool_resp_final", exec_result)
        else:
            yield TextBlock("warn", "没有正确生成python代码失败。")


