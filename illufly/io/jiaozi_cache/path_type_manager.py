from typing import Any, Dict, List, Type, Union, Optional, Tuple, Set, Callable
from enum import Enum
import re
from pydantic import BaseModel
from dataclasses import dataclass
import msgpack
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import get_origin, get_args

class PathType(Enum):
    """路径类型"""
    INDEXABLE = "indexable"    # 可索引路径，指向基础类型值
    STRUCTURAL = "structural"  # 结构路径，指向复合类型，不用于索引

@dataclass
class PathTypeInfo:
    """路径类型信息"""
    path: str                    # 字段路径
    type_name: str              # 类型名称
    path_type: PathType         # 路径类型
    is_tag_list: bool = False   # 是否为标签列表
    max_tags: int = 100         # 标签列表最大长度
    description: str = ""       # 类型说明

    @property
    def is_indexable(self) -> bool:
        """是否可以建立反向索引"""
        return self.path_type == PathType.INDEXABLE

class PathError(Exception):
    """路径相关错误的基类"""
    pass

class PathNotFoundError(PathError):
    """路径不存在错误"""
    def __init__(self, path: str, namespace: str, invalid_part: str):
        self.path = path
        self.namespace = namespace
        self.invalid_part = invalid_part
        super().__init__(f"在命名空间 '{namespace}' 中找不到路径 '{path}' 的部分 '{invalid_part}'")

class PathTypeError(PathError):
    """路径类型错误"""
    def __init__(self, path: str, expected_type: str, actual_type: str):
        self.path = path
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(f"路径 '{path}' 期望类型为 {expected_type}，实际类型为 {actual_type}")

class PathValidationError(PathError):
    """路径验证错误"""
    pass

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

    # 可索引的基础类型
    INDEXABLE_TYPES = {
        str: "str",
        int: "int",
        float: "float",
        bool: "bool",
        bytes: "bytes",
    }

    def __init__(self):
        """初始化路径类型管理器"""
        self._path_types: Dict[str, Dict[str, PathTypeInfo]] = {}
        self._type_registry: Dict[str, Callable] = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "bytes": bytes,
        }
    
    def _get_path_type(self, type_hint: Type) -> PathType:
        """确定类型的路径类型"""
        # 获取基础类型
        origin = get_origin(type_hint) or type_hint
        
        # 处理基础类型
        if origin in self.INDEXABLE_TYPES:
            return PathType.INDEXABLE
            
        # 处理列表类型
        if origin in (list, List):
            args = get_args(type_hint)
            if args and args[0] in self.INDEXABLE_TYPES:
                return PathType.INDEXABLE  # 基础类型的列表视为可索引
            return PathType.STRUCTURAL
            
        # 其他复合类型
        return PathType.STRUCTURAL
    
    def get_indexable_paths(self, namespace: str) -> List[str]:
        """获取指定命名空间下所有可索引的路径"""
        if namespace not in self._path_types:
            return []
            
        return [
            path for path, info in self._path_types[namespace].items()
            if info.is_indexable
        ]
    
    def register_path(self, 
                     path: str,
                     type_name: str,
                     namespace: str,
                     path_type: PathType,
                     is_tag_list: bool = False,
                     max_tags: int = 100,
                     description: str = "") -> None:
        """注册单个路径"""
        if not path:
            raise PathValidationError("路径不能为空")
            
        if not namespace:
            raise PathValidationError("命名空间不能为空")
            
        # 验证路径类型
        if is_tag_list and path_type != PathType.INDEXABLE:
            raise PathValidationError(f"标签列表路径 '{path}' 必须是可索引类型")
            
        # 确保命名空间存在
        if namespace not in self._path_types:
            self._path_types[namespace] = {}
            
        self._path_types[namespace][path] = PathTypeInfo(
            path=path,
            type_name=type_name,
            path_type=path_type,
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
        if isinstance(obj, dict):
            for key, value in obj.items():
                field_path = f"{parent_path}.{key}" if parent_path else key
                
                # 获取字段配置
                config = path_configs.get(field_path, {})
                is_tag_list = config.get("is_tag_list", False)
                
                # 确定路径类型
                if is_tag_list:
                    if not isinstance(value, (list, tuple)) or not all(isinstance(x, str) for x in value):
                        raise PathValidationError(f"标签列表 {field_path} 必须是字符串列表")
                    path_type = PathType.INDEXABLE
                else:
                    path_type = self._get_path_type(type(value))
                
                # 注册当前字段
                self.register_path(
                    path=field_path,
                    type_name=config.get("type_name", type(value).__name__),
                    namespace=namespace,
                    path_type=path_type,
                    is_tag_list=is_tag_list,
                    max_tags=config.get("max_tags", 100),
                    description=config.get("description", "")
                )
                
                # 处理嵌套字段
                if isinstance(value, (dict, BaseModel)):
                    nested_config = config.get("nested", {})
                    self._register_nested_fields(value, field_path, namespace, nested_config)
    
    def register_object(self, 
                       obj: Any, 
                       namespace: Optional[str] = None,
                       path_configs: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        """注册对象或类及其路径信息"""
        if path_configs is None:
            path_configs = {}
        
        # 确定命名空间
        if namespace is None:
            if isinstance(obj, type):
                namespace = obj.__name__
            else:
                namespace = obj.__class__.__name__
        
        # 如果是类而不是实例
        if isinstance(obj, type):
            if issubclass(obj, BaseModel):
                self._register_model_fields(obj, "", namespace, path_configs)
            else:
                self._register_annotated_fields(obj, "", namespace, path_configs)
        elif isinstance(obj, BaseModel):
            # 如果是 Pydantic 模型实例
            self._register_model_fields(obj.__class__, "", namespace, path_configs)
        elif isinstance(obj, dict):
            # 如果是字典
            self._register_dict_fields(obj, "", namespace, path_configs)
        else:
            # 其他类型的实例
            self._register_annotated_fields(obj.__class__, "", namespace, path_configs)

    def _register_model_fields(self,
                             model_class: Type[BaseModel],
                             parent_path: str,
                             namespace: str,
                             path_configs: Dict[str, Dict[str, Any]]) -> None:
        """从 Pydantic 模型类注册字段"""
        for field_name, field in model_class.model_fields.items():
            field_path = f"{parent_path}.{field_name}" if parent_path else field_name
            
            # 获取字段配置
            config = path_configs.get(field_path, {})
            is_tag_list = config.get("is_tag_list", False)
            
            # 确定路径类型
            field_type = field.annotation
            path_type = self._get_path_type(field_type)
            
            # 验证标签列表配置
            if is_tag_list:
                if not (hasattr(field_type, "__origin__") and field_type.__origin__ in (list, List)):
                    raise PathValidationError(f"字段 {field_path} 被标记为标签列表，但类型不是列表")
                element_type = field_type.__args__[0] if hasattr(field_type, "__args__") else None
                if element_type != str:
                    raise PathValidationError(f"标签列表 {field_path} 的元素类型必须是字符串，当前类型是 {element_type}")
                path_type = PathType.INDEXABLE
            
            # 注册当前字段
            self.register_path(
                path=field_path,
                type_name=config.get("type_name", field_type.__name__),
                namespace=namespace,
                path_type=path_type,
                is_tag_list=is_tag_list,
                max_tags=config.get("max_tags", 100),
                description=config.get("description", "")
            )
            
            # 处理嵌套字段
            if path_type == PathType.STRUCTURAL:
                if isinstance(field_type, type) and issubclass(field_type, BaseModel):
                    nested_config = config.get("nested", {})
                    self._register_model_fields(field_type, field_path, namespace, nested_config)
                elif (hasattr(field_type, "__origin__") and 
                      field_type.__origin__ in (list, List) and
                      hasattr(field_type, "__args__")):
                    element_type = field_type.__args__[0]
                    if isinstance(element_type, type) and issubclass(element_type, BaseModel):
                        array_path = f"{field_path}[*]"
                        nested_config = config.get("nested", {})
                        self._register_model_fields(element_type, array_path, namespace, nested_config)

    def _register_annotated_fields(self,
                                 cls: Type,
                                 parent_path: str,
                                 namespace: str,
                                 path_configs: Dict[str, Dict[str, Any]]) -> None:
        """从类型注解注册字段"""
        if hasattr(cls, "__annotations__"):
            for field_name, field_type in cls.__annotations__.items():
                field_path = f"{parent_path}.{field_name}" if parent_path else field_name
                
                # 获取字段配置
                config = path_configs.get(field_path, {})
                
                # 注册当前字段
                self.register_path(
                    path=field_path,
                    type_name=config.get("type_name", getattr(field_type, "__name__", str(field_type))),
                    namespace=namespace,
                    path_type=self._get_path_type(field_type),
                    is_tag_list=config.get("is_tag_list", False),
                    max_tags=config.get("max_tags", 100),
                    description=config.get("description", "")
                )
    
    def _register_dict_fields(self,
                             obj: Dict,
                             parent_path: str,
                             namespace: str,
                             path_configs: Dict[str, Dict[str, Any]]) -> None:
        """从字典注册字段"""
        for key, value in obj.items():
            field_path = f"{parent_path}.{key}" if parent_path else key
            
            # 获取字段配置
            config = path_configs.get(field_path, {})
            is_tag_list = config.get("is_tag_list", False)
            
            # 确定路径类型
            path_type = self._get_path_type(type(value))
            
            # 验证标签列表配置
            if is_tag_list:
                if not isinstance(value, (list, tuple)) or not all(isinstance(x, str) for x in value):
                    raise PathValidationError(f"标签列表 {field_path} 必须是字符串列表")
                path_type = PathType.INDEXABLE
            
            # 注册当前字段
            self.register_path(
                path=field_path,
                type_name=config.get("type_name", type(value).__name__),
                namespace=namespace,
                path_type=path_type,
                is_tag_list=is_tag_list,
                max_tags=config.get("max_tags", 100),
                description=config.get("description", "")
            )
            
            # 处理嵌套字段
            if isinstance(value, dict):
                nested_config = config.get("nested", {})
                self._register_dict_fields(value, field_path, namespace, nested_config)
            elif isinstance(value, (list, tuple)) and value and isinstance(value[0], dict):
                array_path = f"{field_path}[*]"
                nested_config = config.get("nested", {})
                self._register_dict_fields(value[0], array_path, namespace, nested_config)
    
    def extract_and_convert_value(self, obj: Any, path: str, namespace: str) -> Tuple[Any, List[str]]:
        """提取并转换值"""
        if namespace not in self._path_types:
            raise PathNotFoundError(path, namespace, namespace)
            
        # 获取路径类型信息
        type_info = self._path_types[namespace].get(path)
        if type_info and type_info.path_type == PathType.STRUCTURAL:
            raise PathTypeError(path, "indexable", "structural")
            
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
                try:
                    if hasattr(current, base_name):
                        current = getattr(current, base_name)
                    elif isinstance(current, dict):
                        if base_name not in current:
                            raise PathNotFoundError(path, namespace, base_name)
                        current = current[base_name]
                    else:
                        raise PathNotFoundError(path, namespace, base_name)
                except Exception as e:
                    if not isinstance(e, PathError):
                        raise PathNotFoundError(path, namespace, base_name) from e
                    raise
                
                # 处理索引
                try:
                    index = int(index_str)
                    if not isinstance(current, (list, tuple)):
                        raise PathTypeError(path, "list/tuple", type(current).__name__)
                    if index >= len(current):
                        raise PathValidationError(f"路径 '{path}' 的索引 {index} 超出范围 [0, {len(current)})")
                    current = current[index]
                except ValueError:
                    raise PathValidationError(f"路径 '{path}' 包含无效的数组索引: '{index_str}'")
                except Exception as e:
                    if not isinstance(e, PathError):
                        raise PathValidationError(f"访问路径 '{path}' 时发生错误: {str(e)}")
                    raise
            else:
                # 处理普通字段
                try:
                    if hasattr(current, part):
                        current = getattr(current, part)
                    elif isinstance(current, dict):
                        if part not in current:
                            raise PathNotFoundError(path, namespace, part)
                        current = current[part]
                    else:
                        raise PathNotFoundError(path, namespace, part)
                except Exception as e:
                    if not isinstance(e, PathError):
                        raise PathNotFoundError(path, namespace, part) from e
                    raise
        
        # 获取类型信息并进行转换
        if type_info:
            if type_info.is_tag_list:
                if not isinstance(current, (list, tuple)):
                    raise PathTypeError(path, "list/tuple", type(current).__name__)
                return list(current[:type_info.max_tags]), processed_parts
                
            target_type = self._type_registry.get(type_info.type_name)
            if target_type:
                try:
                    return target_type(current), processed_parts
                except (ValueError, TypeError) as e:
                    raise PathTypeError(path, type_info.type_name, type(current).__name__) from e
                
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
                path_type=info["path_type"],
                is_tag_list=info["is_tag_list"],
                max_tags=info["max_tags"],
                description=info["description"]
            )
        
        return manager