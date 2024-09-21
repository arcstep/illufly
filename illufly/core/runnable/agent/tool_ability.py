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
    def tool_desc(self) -> Dict[str, Any]:
        """
        当作为工具时的自描述信息。

        内容参考了 openai 的工具描述规格生成。
        """
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
    
    # @classmethod
    # def dataset_desc(cls, data: Dict[str, "Dataset"]):
    #     """
    #     作为可以使用工具的智能体，罗列所有可用数据集的描述信息。
    #     """
    #     datasets = []
    #     for ds in data.keys():
    #         head = data[ds].df.head()
    #         example_md = head.to_markdown(index=False)
    #         datasets.append(textwrap.dedent(f"""
    #         ------------------------------
    #         **数据集名称：**
    #         {ds}
            
    #         **部份数据样例：**

    #         """) + example_md)

    #     return '\n'.join(datasets)
    
