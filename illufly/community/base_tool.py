from typing import AsyncGenerator, Dict, Any, List, Union, Annotated, Type, Literal
from pydantic import BaseModel, create_model, Field
from pydantic.fields import FieldInfo
from typing import get_origin, get_args

import inspect
import json
import logging

logger = logging.getLogger(__name__)

class BaseToolMeta(type):
    """元类用于校验子类实现"""
    def __new__(cls, name, bases, attrs):
        # 强制要求实现类方法异步生成器 call
        call_method = attrs.get('call', None)
        
        # 检查是否存在call方法
        if not call_method:
            raise TypeError(f"工具类 {name} 必须实现类方法 'call'")
            
        # 验证是否为类方法且是异步生成器
        is_valid = (
            isinstance(call_method, classmethod) and 
            inspect.isasyncgenfunction(call_method.__func__)
        )
        
        if not is_valid:
            raise TypeError(
                f"工具类 {name} 的 call 方法必须同时满足：\n"
                "1. 使用 @classmethod 装饰器\n"
                "2. 定义为 async generator 形式（包含 yield 语句）"
            )
            
        return super().__new__(cls, name, bases, attrs)

class BaseTool(metaclass=BaseToolMeta):
    """工具基类"""
    name: str = None
    description: str = None
    args_schema: BaseModel = None
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # 基础校验
        if not hasattr(cls, 'name'):
            raise TypeError("工具类必须定义name属性")
        if not hasattr(cls, 'description'):
            raise TypeError("工具类必须定义description属性")
        if not hasattr(cls, 'call'):
            raise TypeError("必须实现call方法")
        
        if cls.args_schema is None:
            if 'get_parameters' in cls.__dict__:
                cls._generate_args_from_get_parameters()
            else:
                cls._generate_args_from_call_signature()
        
        # 新增统一参数校验
        cls._validate_parameters()

    @classmethod
    def _generate_args_from_get_parameters(cls):
        """方式1：从get_parameters生成参数模型"""
        parameters = cls.get_parameters()
        fields = {}
        for name, param in parameters.items():
            # 保留原有参数解析逻辑
            if len(param) == 1:
                type_hint = param[0]
                description = "无描述"
                default = ...
            elif len(param) == 2:
                type_hint, description = param
                default = ...
            elif len(param) == 3:
                type_hint, description, default = param
            else:
                raise ValueError(f"参数'{name}'定义格式错误")

            if not is_json_serializable(type_hint):
                raise TypeError(f"参数'{name}'类型{type_hint}无法转换为JSON Schema")
            
            fields[name] = (
                type_hint,
                Field(default=default, description=description)
            )
        
        cls.args_schema = create_model(
            f"{cls.name}Args",
            **fields,
            __base__=BaseModel
        )

    @classmethod
    def _generate_args_from_call_signature(cls):
        """方式2：从call签名推断参数模型"""
        sig = inspect.signature(cls.call)
        fields = {}
        for name, param in sig.parameters.items():
            # 保留原有签名解析逻辑
            if name == "cls":
                continue
                
            type_hint = param.annotation
            description = "无描述"
            default = param.default
            has_default = default != inspect.Parameter.empty
            
            # 处理Annotated类型
            field_meta = None
            if get_origin(type_hint) is Annotated:
                args = get_args(type_hint)
                type_hint = args[0]
                for meta in args[1:]:
                    if isinstance(meta, FieldInfo):
                        field_meta = meta
                        break
            
            if field_meta and field_meta.description:
                description = field_meta.description
            
            # 创建字段
            field = Field(
                default=default if has_default else ...,
                description=description
            )
            
            fields[name] = (type_hint, field)
        
        cls.args_schema = create_model(
            f"{cls.name}Args",
            **fields,
            __base__=BaseModel
        )

    @classmethod
    def _validate_parameters(cls):
        """统一参数校验"""
        for name, field in cls.args_schema.model_fields.items():
            # 处理Optional类型
            type_hint = field.annotation
            if get_origin(type_hint) is Union:
                args = get_args(type_hint)
                non_none_args = [a for a in args if a is not type(None)]
                if len(non_none_args) == 1:
                    type_hint = non_none_args[0]

            if not is_json_serializable(type_hint):
                allowed_types = [
                    "str", "int", "float", "bool", 
                    "Optional", "List", "Dict", "Literal"]
                raise TypeError(
                    f"参数 '{name}' 类型 {type_hint} 不符合要求\n"
                    f"允许的类型：{', '.join(allowed_types)}"
                )

    @classmethod
    def get_parameters(cls) -> Dict[str, Any]:
        """获取参数结构（子类可覆盖）"""
        return {}
    
    @classmethod
    def to_openai(cls) -> dict:
        """生成OpenAI工具描述"""
        schema = cls.args_schema.model_json_schema()
        
        # 构建基础schema结构
        cleaned_schema = {
            "type": "object",
            "properties": {},
            "required": schema.get("required", [])  # 直接使用Pydantic生成的required列表
        }
        
        # 从properties中只保留type和description字段
        for name, prop in schema.get("properties", {}).items():
            cleaned_schema["properties"][name] = {
                "type": prop["type"],
                "description": prop.get("description", "")
            }
        
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": cleaned_schema
            }
        }
    
    @classmethod
    async def call(self, **kwargs) -> AsyncGenerator[str, None]:
        """
        工具调用入口（必须实现为异步生成器）
        最后应返回最终结果字符串
        """
        yield NotImplementedError("Tool call method not implemented")

def is_json_serializable(t: Type) -> bool:
    """严格检查类型是否可安全转换为JSON Schema"""
    # 处理Annotated类型
    origin = get_origin(t)
    if origin is Annotated:
        args = get_args(t)
        return is_json_serializable(args[0])  # 递归检查基础类型
    
    # 处理泛型类型
    origin = origin or t
    
    # 基础类型
    if origin in (str, int, float, bool, type(None)):
        return True
    
    # 处理Optional类型
    if origin is Union:
        args = get_args(t)
        if len(args) == 2 and type(None) in args:
            return is_json_serializable(args[0] if args[1] is type(None) else args[1])
    
    # 处理List类型（包括未参数化的list）
    if origin is list:
        try:
            item_type = get_args(t)[0] if get_args(t) else Any
        except IndexError:
            return False
        # 允许未参数化的列表（视为List[Any]）
        return item_type is Any or is_json_serializable(item_type)
    
    # 处理Dict类型（包括未参数化的dict）
    if origin is dict:
        try:
            key_type, value_type = get_args(t) if get_args(t) else (Any, Any)
        except ValueError:
            return False
        # 允许未参数化的字典（视为Dict[Any, Any]）
        return (is_json_serializable(key_type) or key_type is Any) and \
               (is_json_serializable(value_type) or value_type is Any)
    
    # 其他类型视为不可序列化
    return False
