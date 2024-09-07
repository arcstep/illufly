from typing import Dict, Any
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from ...io import stream_log, yield_block
from ...hub import load_chat_template

from ...desk.state import Dataset

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


def create_python_code_tool(data: Dict[str, Dataset], llm: Any, **kwargs):
    def data_desc():
        datasets = []
        for ds in data.keys():
            head = data[ds].df.head()
            example_md = head.to_markdown(index=False)
            datasets.append(textwrap.dedent(f"""
            ------------------------------
            **数据集名称：**
            {ds}
            
            **部份数据样例：**

            """) + example_md)

        return '\n'.join(datasets)

    def python_code(question: str):
        prompt_template = load_chat_template("GEN_CODE_PANDAS")
        system_prompt = prompt_template.format(datasets=data_desc(), question=question)

        messages = [
            {
                'role': 'system',
                'content': system_prompt
            },
            {
                'role': 'user',
                'content': '请开始'
            }
        ]

        log = stream_log(llm, messages, model=llm, **kwargs)

        code = parse_code(log['output'])
        if code:
            resp = execute_code(data, code)
            return convert_to_text(resp)
        else:
            return "没有正确生成python代码失败。"

    class PythonCodeInput(BaseModel):
        question: str = Field(description="任务或问题的描述")
    
    dataset_names = ', '.join(data.keys())
    dataset_desc = '\n - '.join([ds.desc for ds in data.values()])

    return StructuredTool.from_function(
        func=python_code,
        name="python_code",
        description=f"回答关于{dataset_names}的数据查询和分析的问题。\n具体包括：{dataset_desc}",
        args_schema=PythonCodeInput
    )

def convert_to_text(d):
    if isinstance(d, (np.int64, np.int32, np.uint8)):
        return str(int(d))
    elif isinstance(d, (np.float64, np.float32)):
        return str(float(d))
    elif isinstance(d, dict):
        return ', '.join(f"{k}: {convert_to_text(v)}" for k, v in d.items())
    elif isinstance(d, list):
        return ', '.join(convert_to_text(v) for v in d)
    elif isinstance(d, np.ndarray):
        return ', '.join(map(str, d.tolist()))
    elif isinstance(d, pd.DataFrame):
        return "\n" + d.to_markdown(index=False)
    elif isinstance(d, pd.Series):
        return d.to_markdown(index=False)
    elif isinstance(d, (str, int, float)):
        return str(d)
    else:
        return str(d)  # Fallback to string conversion for any other type

