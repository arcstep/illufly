import inspect
import json
import textwrap

from typing import Any, Callable, Dict, List

class ToolAbility:
    def __init__(self, *, func: Callable = None, name: str = None, description: str = None, parameters: Dict[str, Any] = None, **kwargs):
        self.func = func or self.call
        self.name = name or self.__class__.__name__
        self.description = description or "我还没有工具描述"
        self.parameters = self._get_parameters(parameters)

    def _get_parameters(self, parameters: Dict[str, Any]=None):
        _parameters = parameters or {
            "type": "object",
            "properties": {},
            "required": []
        }
        sig = inspect.signature(self.func)
        for name, param in sig.parameters.items():
            param_value = param.default if param.default is not inspect.Parameter.empty else ""
            
            # 将所有参数值转换为字符串
            param_value = str(param_value)

            _parameters["properties"][name] = {
                "type": "string",  # 统一为 string 类型
                "description": param_value
            }
            if param.default is inspect.Parameter.empty:
                _parameters["required"].append(name)
        return _parameters

    @property
    def tool_desc(self) -> Dict[str, Any]:
        """
        当作为工具时的自描述信息。

        内容参考了 openai 的工具描述规格生成。
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    @staticmethod
    def parse_arguments(arguments: str) -> Dict[str, Any]:
        """
        解析 arguments 字符串并转换为相应的 Python 类型。
        """
        parsed_arguments = json.loads(arguments)
        for key, value in parsed_arguments.items():
            if value.isdigit():
                parsed_arguments[key] = int(value)
            else:
                try:
                    parsed_arguments[key] = float(value)
                except ValueError:
                    if value.lower() == "true":
                        parsed_arguments[key] = True
                    elif value.lower() == "false":
                        parsed_arguments[key] = False
        return parsed_arguments


