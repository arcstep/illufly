from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, Union, Tuple, NamedTuple
from dataclasses import dataclass
from pydantic import BaseModel
from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID
from pathlib import Path
import re
import logging

from .path_types import PathType
from .path_parser import PathSegment, SegmentType

logger = logging.getLogger(__name__)

@dataclass
class TypeInfo:
    """类型信息
    
    用于描述对象的类型信息，包括:
    - 类型名称
    - 原始类型
    - 是否是容器类型
    - 键类型（对于字典）
    - 元素类型（对于容器）
    - 是否可空

    Attributes:
        type_name: 类型名称，如 "dict[str,int]"
        original_type: 原始Python类型
        is_container: 是否是容器类型
        key_type: 键类型（对于字典）
        element_type: 元素类型（对于容器）
        is_nullable: 是否可空
    """

    type_name: str                      # 类型名称
    original_type: Type                 # 原始类型
    is_container: bool = False          # 是否是容器类型
    element_type: Optional[str] = None  # 元素类型（对于容器）
    key_type: Optional[str] = None      # 键类型（对于字典）
    is_nullable: bool = False           # 是否可空
    
class TypeHandler(ABC):
    """类型处理器基类 - 处理特定类型的路径生成和值提取
    
    职责:
    1. 生成对象的所有可能访问路径
    2. 根据路径段提取对象中的值
    3. 获取对象的类型信息
    4. 获取对象的嵌套字段
    
    子类需要实现:
        can_handle(obj): 判断是否可以处理该对象
        get_type_info(obj): 获取对象的类型信息
        get_paths(obj, parent_path=""): 生成所有可能的访问路径
        extract_value(obj, segment): 根据路径段提取值
        get_nested_fields(obj): 获取嵌套字段列表
        parse_segment(path: str) -> Optional[PathSegment]: 解析路径段
    """
    
    @abstractmethod
    def can_handle(self, obj: Any) -> bool:
        """判断是否可以处理该类型"""
        pass
    
    @abstractmethod
    def get_type_info(self, obj: Any) -> TypeInfo:
        """获取类型信息"""
        pass
    
    def infer_access_method(self, obj: Any, field_name: str) -> str:
        """推断字段的访问方式
        
        Returns:
            str: "dot" 表示使用点号访问，"bracket" 表示使用方括号访问
        """
        # 默认使用点号访问
        return "dot"
    
    def get_paths(self, obj: Any, parent_path: str = "") -> List[Tuple[str, str, PathType, str]]:
        """获取所有可能的路径
        
        Returns:
            List[Tuple[str, str, PathType, str]]: (路径, 类型名, 路径类型, 访问方式)
        """
        pass
    
    @abstractmethod
    def get_nested_fields(self, obj: Any) -> List[Tuple[str, Any]]:
        """获取嵌套字段"""
        pass
    
    @abstractmethod
    def extract_value(self, obj: Any, segment: PathSegment) -> Any:
        """提取指定路径段的值"""
        pass
    
    def validate_value(self, value: Any, type_info: TypeInfo) -> bool:
        """验证值是否符合类型要求"""
        if value is None:
            return type_info.is_nullable
            
        if type_info.is_container:
            if isinstance(value, (list, tuple)):
                return all(isinstance(item, type_info.original_type) for item in value)
            elif isinstance(value, dict):
                return all(
                    isinstance(k, eval(type_info.key_type)) and 
                    isinstance(v, type_info.original_type) 
                    for k, v in value.items()
                )
        return isinstance(value, type_info.original_type)
    
    @abstractmethod
    def parse_segment(self, path: str) -> Optional[PathSegment]:
        """解析路径段
        
        Args:
            path: 要解析的路径字符串
            
        Returns:
            Optional[PathSegment]: 解析出的路径段，如果无法解析则返回None
            
        Example:
            DictHandler: "user.name" -> ATTRIBUTE("user")
            ListHandler: "[0]" -> LIST_INDEX("0")
            SimpleHandler: "value" -> ATTRIBUTE("value")
        """
        pass

class SimpleTypeHandler(TypeHandler):
    """简单类型处理器"""
    
    SIMPLE_TYPES = {
        str: TypeInfo(type_name="str", original_type=str),
        int: TypeInfo(type_name="int", original_type=int),
        float: TypeInfo(type_name="float", original_type=float),
        bool: TypeInfo(type_name="bool", original_type=bool),
        bytes: TypeInfo(type_name="bytes", original_type=bytes),
        datetime: TypeInfo(type_name="datetime", original_type=datetime),
        date: TypeInfo(type_name="date", original_type=date),
        time: TypeInfo(type_name="time", original_type=time),
        Decimal: TypeInfo(type_name="decimal", original_type=Decimal),
        UUID: TypeInfo(type_name="uuid", original_type=UUID),
        Path: TypeInfo(type_name="path", original_type=Path),
    }
    
    def can_handle(self, obj: Any) -> bool:
        return type(obj) in self.SIMPLE_TYPES or \
               (isinstance(obj, type) and obj in self.SIMPLE_TYPES)
    
    def get_type_info(self, obj: Any) -> TypeInfo:
        obj_type = obj if isinstance(obj, type) else type(obj)
        return self.SIMPLE_TYPES[obj_type]
    
    def get_paths(self, obj: Any, parent_path: str = "") -> List[Tuple[str, str, PathType, str]]:
        type_info = self.get_type_info(obj)
        return [(parent_path, type_info.type_name, PathType.REVERSIBLE, "dot")]
    
    def get_nested_fields(self, obj: Any) -> List[Tuple[str, Any]]:
        return []  # 简单类型没有嵌套字段
    
    def extract_value(self, obj: Any, segment: PathSegment) -> Any:
        if segment.type != SegmentType.ATTRIBUTE:
            raise ValueError(f"简单类型不支持 {segment.type} 访问")
        return obj
    
    def parse_segment(self, path: str) -> Optional[PathSegment]:
        """解析简单类型的路径段"""
        # 修改：检查是否是字典键访问
        if '.' in path:
            key = path.split('.')[0]
            return PathSegment(
                type=SegmentType.DICT_KEY,  # 修改：使用DICT_KEY类型
                value=key,
                original=key,
                access_method='dot'
            )
        elif path.isidentifier():  # 仅当是有效的标识符时才作为属性处理
            return PathSegment(
                type=SegmentType.ATTRIBUTE,
                value=path,
                original=path,
                access_method='dot'
            )
        return None

class ListHandler(TypeHandler):
    """列表处理器"""
    
    def can_handle(self, obj: Any) -> bool:
        return isinstance(obj, (list, List)) or \
               (isinstance(obj, type) and issubclass(obj, (list, List)))
    
    def get_type_info(self, obj: Any) -> TypeInfo:
        if not obj or isinstance(obj, type):
            return TypeInfo(
                type_name="list",
                original_type=list,
                is_container=True,
                element_type="any"
            )
        
        # 推断元素类型
        element_type = type(obj[0]).__name__ if obj else "any"
        return TypeInfo(
            type_name=f"list[{element_type}]",
            original_type=list,
            is_container=True,
            element_type=element_type
        )
    
    def infer_access_method(self, obj: Any, field_name: str) -> str:
        # 列表总是使用方括号访问
        return "bracket"
    
    def get_paths(self, obj: Any, parent_path: str = "") -> List[Tuple[str, str, PathType, str]]:
        type_info = self.get_type_info(obj)
        paths = []
        
        # 添加基本路径
        if parent_path:
            paths.append((parent_path, type_info.type_name, PathType.NOT_REVERSIBLE, "dot"))
        
        # 对于列表元素，使用方括号访问
        if isinstance(obj, list):
            for i, item in enumerate(obj):
                item_path = f"{parent_path}[{i}]" if parent_path else f"[{i}]"
                paths.append((item_path, type(item).__name__, PathType.REVERSIBLE, "bracket"))
                
        # 通配符路径
        wildcard_path = f"{parent_path}[*]" if parent_path else "[*]"
        paths.append((wildcard_path, type_info.element_type, PathType.NOT_REVERSIBLE, "bracket"))
        
        return paths
    
    def get_nested_fields(self, obj: Any) -> List[Tuple[str, Any]]:
        if not isinstance(obj, list):
            return []
            
        nested_fields = []
        for i, item in enumerate(obj):
            if isinstance(item, (dict, list)) or hasattr(item, '__dict__'):
                nested_fields.append((f"[{i}]", item))
        return nested_fields
    
    def extract_value(self, obj: Any, segment: PathSegment) -> Any:
        if segment.type != SegmentType.LIST_INDEX:
            raise ValueError(f"列表不支持 {segment.type} 访问")
            
        if segment.is_wildcard:
            return obj
            
        index = int(segment.value)
        if not (0 <= index < len(obj)):
            raise IndexError(f"列表索引越界: {index}")
            
        return obj[index]
    
    def parse_segment(self, path: str) -> Optional[PathSegment]:
        """解析列表相关的路径段
        
        支持的格式:
        - [0] - 列表索引
        - [*] - 列表通配符
        """
        if match := re.match(r'^\[([0-9*]+)\]', path):
            value = match.group(1)
            return PathSegment(
                type=SegmentType.LIST_INDEX,
                value=value,
                original=f"[{value}]",
                is_wildcard=(value == '*')
            )
        return None

class DictHandler(TypeHandler):
    """字典处理器"""
    
    def can_handle(self, obj: Any) -> bool:
        return isinstance(obj, dict) or \
               (isinstance(obj, type) and issubclass(obj, dict))
    
    def get_type_info(self, obj: Any) -> TypeInfo:
        if not obj or isinstance(obj, type):
            return TypeInfo(
                type_name="dict",
                original_type=dict,
                is_container=True,
                key_type="str",
                element_type="any"
            )
        
        # 推断键值类型
        key_type = type(next(iter(obj.keys()))).__name__ if obj else "any"
        value_type = type(next(iter(obj.values()))).__name__ if obj else "any"
        return TypeInfo(
            type_name=f"dict[{key_type},{value_type}]",
            original_type=dict,
            is_container=True,
            key_type=key_type,
            element_type=value_type
        )
    
    def infer_access_method(self, obj: Any, field_name: str) -> str:
        # 如果键包含特殊字符，使用方括号访问
        if not field_name.isidentifier():
            return "bracket"
        return "dot"
    
    def get_paths(self, obj: Any, parent_path: str = "") -> List[Tuple[str, str, PathType, str]]:
        paths = []
        # 添加根路径
        paths.append((parent_path, "dict", PathType.REVERSIBLE, "dot"))
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                # 构建当前键的路径 - 使用简洁的花括号语法
                if parent_path:
                    current_path = f"{parent_path}{{{key}}}"
                else:
                    current_path = f"{{{key}}}"
                
                # 添加当前路径
                value_type = type(value).__name__
                paths.append((current_path, value_type, PathType.REVERSIBLE, "bracket"))
                
                # 处理嵌套字典
                if isinstance(value, (dict, list)):
                    nested_paths = self.get_paths(value, current_path)
                    paths.extend(nested_paths)
                    
        return paths
    
    def extract_value(self, obj: Any, segment: Union[PathSegment, str]) -> Any:
        """提取值"""
        if not obj:
            raise ValueError("空对象")
            
        # 处理 PathSegment 对象
        if isinstance(segment, PathSegment):
            if segment.type == SegmentType.DICT_KEY:
                try:
                    return obj[segment.value]
                except KeyError as e:
                    raise KeyError(f"键不存在: {e}")
            elif segment.type == SegmentType.ATTRIBUTE:
                # 如果是属性访问，尝试先用属性访问，失败则用键访问
                try:
                    return getattr(obj, segment.value)
                except AttributeError:
                    try:
                        return obj[segment.value]
                    except KeyError as e:
                        raise KeyError(f"键不存在: {e}")
            else:
                raise ValueError(f"字典不支持 {segment.type} 访问")
                
        # 处理字符串路径
        if not isinstance(segment, str):
            raise TypeError(f"期望字符串或PathSegment，得到 {type(segment)}")
            
        # 处理字典键访问 {key}
        if match := re.match(r'\{([^}]+)\}', segment):
            key = match.group(1)
            try:
                return obj[key]
            except KeyError as e:
                raise KeyError(f"键不存在: {e}")
            
        # 处理嵌套路径
        if '.' in segment:
            parts = segment.split('.')
            result = obj
            try:
                for part in parts:
                    # 检查是否是字典键访问
                    if part.startswith('{') and part.endswith('}'):
                        key = part[1:-1]
                        result = result[key]
                    else:
                        # 尝试属性访问，失败则用键访问
                        try:
                            result = getattr(result, part)
                        except AttributeError:
                            result = result[part]
                return result
            except (KeyError, AttributeError) as e:
                raise KeyError(f"访问失败: {e}")
            
        # 直接键访问
        try:
            return obj[segment]
        except KeyError as e:
            raise KeyError(f"键不存在: {e}")
    
    def get_nested_fields(self, obj: Any) -> List[Tuple[str, Any]]:
        """获取嵌套字段"""
        if not isinstance(obj, dict):
            return []
            
        nested_fields = []
        for key, value in obj.items():
            if isinstance(value, (dict, list)) or hasattr(value, '__dict__'):
                nested_fields.append((str(key), value))
        return nested_fields
    
    def parse_segment(self, path: str) -> Optional[PathSegment]:
        """解析字典相关的路径段"""
        # 处理字典键访问 {key}
        if match := re.match(r'\{([^}]+)\}', path):
            value = match.group(1)
            return PathSegment(
                type=SegmentType.DICT_KEY,
                value=value,
                original=path,
                access_method="bracket"
            )
            
        # 处理通配符
        if path == '*':
            return PathSegment(
                type=SegmentType.DICT_KEY,
                value='*',
                original='*',
                is_wildcard=True,
                access_method="dot"
            )
            
        return None


class TupleHandler(TypeHandler):
    """元组处理器"""
    
    def can_handle(self, obj: Any) -> bool:
        return isinstance(obj, tuple) or \
               (isinstance(obj, type) and issubclass(obj, tuple) and not issubclass(obj, NamedTuple))
    
    def get_type_info(self, obj: Any) -> TypeInfo:
        if not obj or isinstance(obj, type):
            return TypeInfo(
                type_name="tuple",
                original_type=tuple,
                is_container=True,
                element_type="any"
            )
        
        # 推断元素类型
        element_types = [type(x).__name__ for x in obj]
        type_str = f"tuple[{','.join(element_types)}]"
        return TypeInfo(
            type_name=type_str,
            original_type=tuple,
            is_container=True,
            element_type=",".join(element_types)
        )
    
    def get_paths(self, obj: Any, parent_path: str = "") -> List[Tuple[str, str, PathType, str]]:
        paths = [(parent_path, "tuple", PathType.NOT_REVERSIBLE, "dot")]
        
        # 如果是实例或具有类型注解，添加索引路径
        if isinstance(obj, tuple):
            for i in range(len(obj)):
                index_path = f"{parent_path}[{i}]"
                paths.append((index_path, str(type(obj[i]).__name__), PathType.REVERSIBLE, "bracket"))
        return paths
    
    def extract_value(self, obj: Any, path: str) -> Any:
        if not path:
            return obj
        match = re.match(r'\[(\d+)\]', path)
        if match:
            index = int(match.group(1))
            return obj[index]
        return obj
    
    def get_nested_fields(self, obj: Any) -> List[Tuple[str, Any]]:
        if not isinstance(obj, tuple):
            return []
            
        nested_fields = []
        for i, item in enumerate(obj):
            if isinstance(item, (dict, list, tuple)) or hasattr(item, '__dict__'):
                nested_fields.append((f"[{i}]", item))
        return nested_fields
    
    def parse_segment(self, path: str) -> Optional[PathSegment]:
        """解析元组相关的路径段"""
        # 元组索引 [0]
        if match := re.match(r'^\[(\d+)\]', path):
            return PathSegment(
                type=SegmentType.LIST_INDEX,
                value=match.group(1),
                original=match.group(0)
            )
            
        return None

class NamedTupleHandler(TypeHandler):
    """命名元组处理器"""
    
    def can_handle(self, obj: Any) -> bool:
        return (isinstance(obj, tuple) and hasattr(obj, '_fields')) or \
               (isinstance(obj, type) and issubclass(obj, NamedTuple))
    
    def get_type_info(self, obj: Any) -> TypeInfo:
        cls = obj if isinstance(obj, type) else obj.__class__
        field_types = getattr(cls, '_field_types', {})
        return TypeInfo(
            type_name=cls.__name__,
            original_type=cls,
            is_container=True,
            element_type=str(field_types),
            metadata={'fields': cls._fields}
        )
    
    def get_paths(self, obj: Any, parent_path: str = "") -> List[Tuple[str, str, PathType, str]]:
        cls = obj if isinstance(obj, type) else obj.__class__
        paths = [(parent_path, cls.__name__, PathType.NOT_REVERSIBLE, "dot")]
        
        # 添加字段路径
        field_types = getattr(cls, '_field_types', {})
        for i, (field_name, field_type) in enumerate(field_types.items()):
            # 属性访问路径
            field_path = f"{parent_path}.{field_name}" if parent_path else field_name
            paths.append((field_path, str(field_type), PathType.REVERSIBLE, "dot"))
            # 索引访问路径
            index_path = f"{parent_path}[{i}]" if parent_path else f"[{i}]"
            paths.append((index_path, str(field_type), PathType.REVERSIBLE, "bracket"))
        return paths
    
    def extract_value(self, obj: Any, path: str) -> Any:
        if not path:
            return obj
        if path.startswith('['):
            match = re.match(r'\[(\d+)\]', path)
            if match:
                index = int(match.group(1))
                return obj[index]
        else:
            attr_name = path.split('.')[0]
            return getattr(obj, attr_name)
        return obj
    
    def get_nested_fields(self, obj: Any) -> List[Tuple[str, Any]]:
        if not isinstance(obj, tuple) or not hasattr(obj, '_fields'):
            return []
            
        nested_fields = []
        for field_name in obj._fields:
            value = getattr(obj, field_name)
            if isinstance(value, (dict, list, tuple)) or hasattr(value, '__dict__'):
                nested_fields.append((field_name, value))
        return nested_fields
    
    def parse_segment(self, path: str) -> Optional[PathSegment]:
        """解析命名元组相关的路径段"""
        # 属性访问 name
        if match := re.match(r'^([^.\[\{]+)', path):
            value = match.group(1)
            return PathSegment(
                type=SegmentType.ATTRIBUTE,
                value=value,
                original=value
            )
            
        # 索引访问 [0]
        if match := re.match(r'^\[(\d+)\]', path):
            return PathSegment(
                type=SegmentType.LIST_INDEX,
                value=match.group(1),
                original=match.group(0)
            )
            
        return None

class EnumHandler(TypeHandler):
    """枚举类型处理器"""
    
    def can_handle(self, obj: Any) -> bool:
        return isinstance(obj, Enum) or \
               (isinstance(obj, type) and issubclass(obj, Enum))
    
    def get_type_info(self, obj: Any) -> TypeInfo:
        cls = obj if isinstance(obj, type) else obj.__class__
        return TypeInfo(
            type_name=cls.__name__,
            original_type=cls,
            is_container=False
        )
    
    def get_paths(self, obj: Any, parent_path: str = "") -> List[Tuple[str, str, PathType, str]]:
        cls = obj if isinstance(obj, type) else obj.__class__
        paths = [(parent_path, cls.__name__, PathType.REVERSIBLE, "dot")]
        
        # 如果是枚举类，添加所有枚举值的路径
        if isinstance(obj, type) and issubclass(obj, Enum):
            for member in obj:
                member_path = f"{parent_path}.{member.name}"
                paths.append((member_path, "enum_value", PathType.REVERSIBLE, "dot"))
        return paths
    
    def extract_value(self, obj: Any, path: str) -> Any:
        if not path:
            return obj
        attr_name = path.split('.')[0]
        if isinstance(obj, type):
            return getattr(obj, attr_name)
        return obj
    
    def get_nested_fields(self, obj: Any) -> List[Tuple[str, Any]]:
        return []  # 枚举类型没有嵌套字段
    
    def parse_segment(self, path: str) -> Optional[PathSegment]:
        """解析枚举相关的路径段"""
        # 枚举成员访问 name
        if match := re.match(r'^([^.\[\{]+)', path):
            value = match.group(1)
            return PathSegment(
                type=SegmentType.ATTRIBUTE,
                value=value,
                original=value
            )
            
        return None

class PydanticHandler(TypeHandler):
    """Pydantic模型处理器"""
    
    def can_handle(self, obj: Any) -> bool:
        return isinstance(obj, BaseModel) or \
               (isinstance(obj, type) and issubclass(obj, BaseModel))
    
    def get_type_info(self, obj: Any) -> TypeInfo:
        model_class = obj if isinstance(obj, type) else obj.__class__
        return TypeInfo(
            type_name=model_class.__name__,
            original_type=model_class,
            is_container=False
        )
    
    def infer_access_method(self, obj: Any, field_name: str) -> str:
        # Pydantic 模型默认使用点号访问
        return "dot"
    
    def get_paths(self, obj: Any, parent_path: str = "") -> List[Tuple[str, str, PathType, str]]:
        model_class = obj if isinstance(obj, type) else obj.__class__
        paths = [(parent_path, model_class.__name__, PathType.REVERSIBLE, "dot")]
        
        for field_name, field in model_class.model_fields.items():
            access_method = self.infer_access_method(obj, field_name)
            field_path = f"{parent_path}.{field_name}" if parent_path else field_name
            field_type = self._get_field_type_name(field)
            paths.append((field_path, field_type, PathType.REVERSIBLE, access_method))
        
        return paths
    
    def get_nested_fields(self, obj: Any) -> List[Tuple[str, Any]]:
        """获取嵌套的Pydantic模型字段"""
        if isinstance(obj, type):
            return []  # 类型本身没有嵌套字段
            
        nested_fields = []
        for field_name, field in obj.model_fields.items():
            field_value = getattr(obj, field_name)
            if isinstance(field_value, (BaseModel, list, dict)):
                nested_fields.append((field_name, field_value))
        return nested_fields
    
    def extract_value(self, obj: Any, segment: PathSegment) -> Any:
        """提取字段值"""
        if segment.type != SegmentType.ATTRIBUTE:
            raise ValueError(f"Pydantic模型不支持 {segment.type} 访问")
            
        if isinstance(obj, type):
            # 如果是类型，返回字段类型信息
            field = obj.model_fields.get(segment.value)
            if not field:
                raise AttributeError(f"字段不存在: {segment.value}")
            return field.annotation
            
        # 如果是实例，返回字段值
        if not hasattr(obj, segment.value):
            raise AttributeError(f"字段不存在: {segment.value}")
        return getattr(obj, segment.value)
    
    def _get_field_type_name(self, field: Any) -> str:
        """获取字段类型名称"""
        annotation = field.annotation
        if hasattr(annotation, "__origin__"):  # 处理泛型类型
            origin = annotation.__origin__
            args = annotation.__args__
            if origin in (list, List):
                return f"list[{args[0].__name__}]"
            elif origin in (dict, Dict):
                return f"dict[{args[0].__name__},{args[1].__name__}]"
        return getattr(annotation, "__name__", str(annotation))
    
    def parse_segment(self, path: str) -> Optional[PathSegment]:
        """解析Pydantic模型相关的路径段"""
        # 字段访问 field_name
        if match := re.match(r'^([^.\[\{]+)', path):
            value = match.group(1)
            return PathSegment(
                type=SegmentType.ATTRIBUTE,
                value=value,
                original=value
            )
            
        return None
