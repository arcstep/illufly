import inspect
import json
import textwrap

from typing import Any, Callable, Dict, List

PYTHON_TO_JSON_TYPES = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
}

class ToolAbility:
    def __init__(self, *, func: Callable = None, name: str = None, description: str = None, parameters: Dict[str, Any] = None, **kwargs):
        self.func = func or self.call
        self.name = name or (func.__name__ if func else self.__class__.__name__)
        self.arguments = func.__annotations__ if func else {}
        self.description = description or (func.__doc__ if func and func.__doc__ else "")
        self.parameters = parameters

    @property
    def tool(self) -> Dict[str, Any]:
        if not self.parameters:
            self.parameters = {
                "type": "object",
                "properties": {},
                "required": []
            }
            sig = inspect.signature(self.func)
            for name, param in sig.parameters.items():
                param_type = self.arguments.get(name, str).__name__
                if param_type in PYTHON_TO_JSON_TYPES:
                    param_type = PYTHON_TO_JSON_TYPES[param_type]
                self.parameters["properties"][name] = {
                    "type": param_type,
                    "description": param.default if param.default is not inspect.Parameter.empty else ""
                }
                if param.default is inspect.Parameter.empty:
                    self.parameters["required"].append(name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
    
    @classmethod
    def tools_desc(cls, tools: List["Runnable"]):
        """
        描述所有可选工具的具体情况。
        """
        tools_list = ",\n".join([json.dumps(t.tool, ensure_ascii=False) for t in tools])
        return f'```json\n[{tools_list}]\n```'

    @classmethod
    def tools_selected(cls, tools: List["Runnable"]):
        """
        描述工具选中的具体情况。
        """
        action_output = {
            "index": "integer: index of selected function",
            "function": {
                "name": "(string): 填写选中参数名称",
                "parameters": "(json): 填��具体参数值"
            }
        }
        name_list = ",".join([a.name for a in tools])
        example = '\n'.join([
            '**工具函数输出示例：**',
            '```json',
            '[{"index": 0, "function": {"name": "get_current_weather", "parameters": "{\"location\": \"广州\"}"}},',
            '{"index": 1, "function": {"name": "get_current_weather", "parameters": "{\"location\": \"上海\"}"}}]',
            '```'
        ])

        output = f'```json <tools-calling>\n[{json.dumps(action_output, ensure_ascii=False)}]\n```'

        return f'从列表 [{name_list}] 中选择一个或多个funciton，并按照下面的格式输出函数描述列表，描述每个函数的名称和参数：\n{output}\n{example}'

    @classmethod
    def dataset_desc(cls, data: Dict[str, "Dataset"]):
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
    
