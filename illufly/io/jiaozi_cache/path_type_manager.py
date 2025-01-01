from typing import Any, Dict, List, Type, Union, Optional, Tuple, Set
from enum import Enum
import re
from pydantic import BaseModel
from dataclasses import dataclass
import msgpack
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from uuid import UUID

@dataclass
class PathTypeInfo:
    """路径类型信息"""
    path: str                    # 字段路径
    type_name: str              # 类型名称
    is_tag_list: bool = False   # 是否为标签列表
    max_tags: int = 100         # 标签列表最大长度
    description: str = ""       # 类型说明

class PathTypeManager:
    """路径和类型管理器"""
    
    BUILTIN_NAMESPACE = "__built_in__"
    
    # 内置支持的类型
    BUILTIN_TYPES = {
        # 基础类型
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        
        # 集合类型
        "tuple": tuple,
        "list": list,
        "dict": dict,
        "set": set,
        "frozenset": frozenset,
        
        # 日期时间类型
        "datetime": datetime,
        "date": datetime.date,
        "time": datetime.time,
        
        # 其他常用类型
        "Decimal": Decimal,
        "UUID": UUID,
        "Path": Path,
    }
    
    def __init__(self):
        """初始化类型注册表"""
        self._path_types: Dict[str, Dict[str, PathTypeInfo]] = {}
        self._type_registry: Dict[str, Type] = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple
        }
    
    def register_path(self, 
                     path: str,
                     type_name: str,
                     namespace: str,
                     is_tag_list: bool = False,
                     max_tags: int = 100,
                     description: str = "") -> None:
        """注册单个路径"""
        if namespace not in self._path_types:
            self._path_types[namespace] = {}
            
        self._path_types[namespace][path] = PathTypeInfo(
            path=path,
            type_name=type_name,
            is_tag_list=is_tag_list,
            max_tags=max_tags,
            description=description
        )
    
    def _register_nested_fields(self, 
                              obj: Any, 
                              parent_path: str,
                              namespace: str,
                              path_configs: Dict[str, Dict[str, Any]]) -> None:
        """递归注册嵌套字段"""
        if isinstance(obj, BaseModel):
            for field_name, field in obj.__class__.model_fields.items():
                field_path = f"{parent_path}.{field_name}" if parent_path else field_name
                field_value = getattr(obj, field_name, None)
                
                # 获取字段配置
                config = path_configs.get(field_path, {})
                
                # 验证标签列表配置
                is_tag_list = config.get("is_tag_list", False)
                if is_tag_list:
                    # 获取字段类型
                    field_type = field.annotation
                    # 检查是否为列表类型
                    if not (hasattr(field_type, "__origin__") and field_type.__origin__ in (list, List)):
                        raise ValueError(f"字段 {field_path} 被标记为标签列表，但类型不是列表")
                    # 获取列表元素类型
                    element_type = field_type.__args__[0] if hasattr(field_type, "__args__") else None
                    if element_type != str:
                        raise ValueError(f"标签列表 {field_path} 的元素类型必须是字符串，当前类型是 {element_type}")
                
                # 注册当前字段
                self.register_path(
                    path=field_path,
                    type_name=config.get("type_name", field.annotation.__name__),
                    namespace=namespace,
                    is_tag_list=is_tag_list,
                    max_tags=config.get("max_tags", 100),
                    description=config.get("description", "")
                )
                
                # 处理嵌套字段
                if isinstance(field_value, (BaseModel, dict)):
                    nested_config = config.get("nested", {})
                    self._register_nested_fields(field_value, field_path, namespace, nested_config)
                elif isinstance(field_value, (list, tuple)) and field_value:
                    if isinstance(field_value[0], (BaseModel, dict)):
                        array_path = f"{field_path}[*]"
                        nested_config = config.get("nested", {})
                        self._register_nested_fields(field_value[0], array_path, namespace, nested_config)
                        
        elif isinstance(obj, dict):
            for key, value in obj.items():
                field_path = f"{parent_path}.{key}" if parent_path else key
                
                # 获取字段配置
                config = path_configs.get(field_path, {})
                
                # 注册当前字段
                self.register_path(
                    path=field_path,
                    type_name=config.get("type_name", type(value).__name__),
                    namespace=namespace,
                    is_tag_list=config.get("is_tag_list", False),
                    max_tags=config.get("max_tags", 100),
                    description=config.get("description", "")
                )
                
                # 处理嵌套字段
                if isinstance(value, (dict, BaseModel)):
                    nested_config = config.get("nested", {})
                    self._register_nested_fields(value, field_path, namespace, nested_config)
                elif isinstance(value, (list, tuple)) and value:
                    if isinstance(value[0], (dict, BaseModel)):
                        array_path = f"{field_path}[*]"
                        nested_config = config.get("nested", {})
                        self._register_nested_fields(value[0], array_path, namespace, nested_config)
    
    def register_object(self, 
                       obj: Any, 
                       namespace: Optional[str] = None,
                       path_configs: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        """注册对象及其路径信息"""
        if namespace is None:
            namespace = obj.__class__.__name__
            
        path_configs = path_configs or {}
        
        # 使用递归方法注册所有字段
        self._register_nested_fields(obj, "", namespace, path_configs)
    
    def extract_and_convert_value(self, obj: Any, path: str, namespace: str) -> Tuple[Any, List[str]]:
        """提取并转换值"""
        parts = path.split('.')
        current = obj
        processed_parts = []
        
        for part in parts:
            processed_parts.append(part)
            
            # 处理数组索引
            if '[' in part and ']' in part:
                base_name = part[:part.index('[')]
                index_str = part[part.index('[')+1:part.index(']')]
                
                # 获取基础字段
                if hasattr(current, base_name):
                    current = getattr(current, base_name)
                elif isinstance(current, dict):
                    if base_name not in current:
                        return None, processed_parts
                    current = current[base_name]
                else:
                    return None, processed_parts
                
                # 处理索引
                try:
                    index = int(index_str)
                    if not isinstance(current, (list, tuple)) or index >= len(current):
                        return None, processed_parts
                    current = current[index]
                except (ValueError, IndexError):
                    return None, processed_parts
            else:
                # 处理普通字段
                if hasattr(current, part):
                    current = getattr(current, part)
                elif isinstance(current, dict):
                    if part not in current:
                        return None, processed_parts
                    current = current[part]
                else:
                    return None, processed_parts
        
        # 获取类型信息并进行转换
        type_info = self._path_types[namespace].get(path)
        if type_info:
            if type_info.is_tag_list and isinstance(current, (list, tuple)):
                return list(current[:type_info.max_tags]), processed_parts
                
            target_type = self._type_registry.get(type_info.type_name)
            if target_type:
                try:
                    return target_type(current), processed_parts
                except (ValueError, TypeError):
                    return None, processed_parts
        
        return current, processed_parts
    
    def serialize_type_info(self) -> bytes:
        """序列化类型信息"""
        data = {
            path: {
                "type_name": info.type_name,
                "is_tag_list": info.is_tag_list,
                "max_tags": info.max_tags,
                "description": info.description
            }
            for path, info in self._path_types.items()
        }
        return msgpack.packb(data, use_bin_type=True)
    
    @classmethod
    def deserialize_type_info(cls, data: bytes) -> 'PathTypeManager':
        """从序列化数据恢复类型信息"""
        manager = cls()
        type_data = msgpack.unpackb(data, raw=False)
        
        for path, info in type_data.items():
            manager.register_path(
                path=path,
                type_name=info["type_name"],
                namespace=info["namespace"],
                is_tag_list=info["is_tag_list"],
                max_tags=info["max_tags"],
                description=info["description"]
            )
        
        return manager