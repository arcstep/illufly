import inspect
import json
import textwrap
from decimal import Decimal

from typing import Any, Callable, Dict, get_origin, get_args, Union, Tuple, Set

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
            param_type = self._get_json_type(param.annotation)
            
            _parameters["properties"][name] = {
                "type": param_type,
                "description": str(param_value)
            }
            if param.default is inspect.Parameter.empty:
                _parameters["required"].append(name)
        return _parameters

    def _get_json_type(self, annotation):
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Union:
            # 处理 Union 类型，返回所有可能的类型
            return [self._get_json_type(arg) for arg in args]
        elif origin is list or annotation is list:
            return "array"
        elif origin is tuple or annotation is tuple:
            # 假设 Tuple 是一个固定长度的数组
            return {
                "type": "array",
                "items": [self._get_json_type(arg) for arg in args] if args else "string"
            }
        elif origin is set or annotation is set:
            # Set 可以被视为一个不允许重复元素的数组
            return {
                "type": "array",
                "uniqueItems": True,
                "items": self._get_json_type(args[0]) if args else "string"
            }
        elif origin is dict or annotation is dict:
            return "object"
        elif annotation is int:
            return "integer"
        elif annotation is float:
            return "number"
        elif annotation is bool:
            return "boolean"
        elif annotation is str:
            return "string"
        else:
            return "string"  # 默认类型

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
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON input: {e}")

        parameter_types = self.parameters.get("properties", {})

        if isinstance(parsed_arguments, list):
            return parsed_arguments
        elif isinstance(parsed_arguments, dict):
            for key, value in parsed_arguments.items():
                expected_type = parameter_types.get(key, {}).get("type", "string")
                
                try:
                    if expected_type == "integer":
                        parsed_arguments[key] = int(value)
                    elif expected_type == "number":
                        parsed_arguments[key] = float(value)
                    elif expected_type == "boolean":
                        if isinstance(value, str):
                            parsed_arguments[key] = value.lower() == "true"
                        else:
                            parsed_arguments[key] = bool(value)
                    elif expected_type == "array":
                        if "uniqueItems" in parameter_types.get(key, {}):
                            parsed_arguments[key] = set(value)
                        elif "items" in parameter_types.get(key, {}):
                            parsed_arguments[key] = tuple(value)
                        else:
                            parsed_arguments[key] = list(value)
                    elif expected_type == "null":
                        parsed_arguments[key] = None
                    elif expected_type == "decimal":
                        parsed_arguments[key] = Decimal(value)
                    else:
                        parsed_arguments[key] = value
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Error converting {key}: {e}")
            return parsed_arguments
        else:
            raise ValueError("Parsed arguments must be a list or a dictionary")




