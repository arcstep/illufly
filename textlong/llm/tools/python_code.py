from typing import Dict, Any
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from ...desk import Desk
from ...io import stream_log, yield_block
from ...hub import load_chat_template

import textwrap
import pandas as pd

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

    # 受限制的全局命名空间
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
        "data": data, # 数据集清单
        "pd": pd  # 仅允许 pandas 模块
    }

    # 受限制的本地命名空间
    restricted_locals = {}

    # 将附加代码添加到现有代码中
    filtered_code = f"{filtered_code}\n\nresult = main()\n"

    try:
        exec(filtered_code, restricted_globals, restricted_locals)
    except Exception as e:
        return f"执行代码时发生错误: {e}"
    
    return restricted_locals.get('result', "生成的代码已经执行，但返回了空结果。")

def create_python_code_tool(data: Dict[str, Any], llm: Any, **kwargs):
    def data_desc():
        datasets = [
            textwrap.dedent(f"""
            ------------------------------
            **数据集名称：**
            {ds}
            
            **数据示例：**

            """) + pd.DataFrame(data[ds]).head().to_markdown(index=False)
            for ds in data.keys()
        ]

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
            if resp:
                return resp
            else:
                return "生成的代码已经执行，但返回了空结果。"
        else:
            return "没有正确生成python代码失败。"

    class PythonCodeInput(BaseModel):
        question: str = Field(description="任务或问题的描述")
    
    return StructuredTool.from_function(
        func=python_code,
        name="python_code",
        description="针对数据集名称和问题生成python代码，并返回执行结果。",
        args_schema=PythonCodeInput
    )

