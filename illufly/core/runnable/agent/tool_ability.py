import inspect
import json
import textwrap

from typing import Any, Callable, Dict, List

class ToolAbility:
    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "func": "用于自定义工具的同步执行函数",
            "async_func": "用于自定义工具的异步执行函数",
            "name": "工具名称",
            "description": "工具描述",
            "tool_params": "工具参数",
        }

    def __init__(
        self,
        *,
        func: Callable = None,
        async_func: Callable = None,
        name: str = None,
        description: str = None,
        tool_params: Dict[str, Any] = None
    ):
        self.func = func
        self.async_func = async_func
        self.description = description or "我还没有工具描述"
        self.tool_params = tool_params or {}

        if name:
            self.name = name

    def get_default_parameters(self):
        _parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        sig = inspect.signature(self.func or self.async_func or self.call)
        for name, param in sig.parameters.items():
            param_value = param.default if param.default is not inspect.Parameter.empty else ""
            
            # 根据参数的注解类型设置 JSON 兼容类型
            param_type = "string"  # 默认类型
            if param.annotation is int:
                param_type = "integer"
            elif param.annotation is float:
                param_type = "number"
            elif param.annotation is bool:
                param_type = "boolean"
            elif param.annotation is str:
                param_type = "string"
            elif param.annotation is list:
                param_type = "array"
            elif param.annotation is dict:
                param_type = "object"
            
            _parameters["properties"][name] = {
                "type": param_type,
                "description": str(param_value)
            }
            if param.default is inspect.Parameter.empty:
                _parameters["required"].append(name)
        return _parameters

    @property
    def parameters(self) -> str:
        default_params = self.get_default_parameters()
        final_params = {'type': default_params["type"], 'properties': {}, 'required': []}
        if not self.tool_params:
            return default_params
        else:
            for prop_name, prop_dict in default_params["properties"].items():
                if prop_name in self.tool_params.keys():
                    final_params["properties"][prop_name] = prop_dict
                    final_params["properties"][prop_name]["description"] = self.tool_params[prop_name]
            final_params["required"] = [k for k in default_params["required"] if k in final_params["properties"].keys()]
            return final_params

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

    def parse_arguments(self, arguments: str) -> Dict[str, Any]:
        """
        解析 arguments 字符串并根据 self.parameters 中的类型信息转换为相应的 Python 类型。
        """
        parsed_arguments = json.loads(arguments)
        parameter_types = self.parameters.get("properties", {})

        if isinstance(parsed_arguments, list):
            return parsed_arguments
        elif isinstance(parsed_arguments, dict):
            for key, value in parsed_arguments.items():
                expected_type = parameter_types.get(key, {}).get("type", "string")
                
                if expected_type == "integer":
                    parsed_arguments[key] = int(value)
                elif expected_type == "number":
                    parsed_arguments[key] = float(value)
                elif expected_type == "boolean":
                    if isinstance(value, str):
                        parsed_arguments[key] = value.lower() == "true"
                    else:
                        parsed_arguments[key] = bool(value)
                else:
                    # 默认转换为字符串
                    parsed_arguments[key] = str(value)
            return parsed_arguments
        else:
            return None




