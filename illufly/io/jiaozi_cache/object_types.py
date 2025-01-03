from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, Union, Tuple, NamedTuple, Set
from dataclasses import dataclass
from pydantic import BaseModel
from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID
from pathlib import Path
from collections import namedtuple
from enum import Enum, auto
import re
import logging

from .path_types import PathType
from .path_parser import PathSegment, SegmentType

logger = logging.getLogger(__name__)

class TypeCategory(Enum):
    """类型分类"""
    STRUCTURE = auto()      # 可作为结构（类、dataclass等）
    INDEXABLE = auto()      # 可建立索引的简单类型
    COLLECTION = auto()     # 集合类型（不建立索引但可以存储）

@dataclass
class TypeInfo:
    """类型信息
    
    用于描述对象的类型信息，包括:
    - 类型名称
    - 原始类型
    - 类型分类（结构/可索引/集合）
    - 是否是容器类型
    - 键类型（对于字典）
    - 元素类型（对于容器）
    - 是否可空
    """
    type_name: str                      # 类型名称
    original_type: Type                 # 原始类型
    category: TypeCategory              # 类型分类
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
        return []
    
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
    """简单类型处理器 - 可索引的基础类型"""
    
    SIMPLE_TYPES = {
        str: TypeInfo(type_name="str", original_type=str, category=TypeCategory.INDEXABLE),
        int: TypeInfo(type_name="int", original_type=int, category=TypeCategory.INDEXABLE),
        float: TypeInfo(type_name="float", original_type=float, category=TypeCategory.INDEXABLE),
        bool: TypeInfo(type_name="bool", original_type=bool, category=TypeCategory.INDEXABLE),
        bytes: TypeInfo(type_name="bytes", original_type=bytes, category=TypeCategory.INDEXABLE),
        datetime: TypeInfo(type_name="datetime", original_type=datetime, category=TypeCategory.INDEXABLE),
        date: TypeInfo(type_name="date", original_type=date, category=TypeCategory.INDEXABLE),
        time: TypeInfo(type_name="time", original_type=time, category=TypeCategory.INDEXABLE),
        Decimal: TypeInfo(type_name="decimal", original_type=Decimal, category=TypeCategory.INDEXABLE),
        UUID: TypeInfo(type_name="uuid", original_type=UUID, category=TypeCategory.INDEXABLE),
        Path: TypeInfo(type_name="path", original_type=Path, category=TypeCategory.INDEXABLE),
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

class CollectionHandler(TypeHandler):
    """集合类型处理器 - 处理 list, dict, tuple 等内置集合类型"""
    
    def can_handle(self, obj: Any) -> bool:
        return isinstance(obj, (list, dict, tuple)) or \
               (isinstance(obj, type) and issubclass(obj, (list, dict, tuple)))
    
    def get_type_info(self, obj: Any) -> TypeInfo:
        if isinstance(obj, (list, List)) or \
           (isinstance(obj, type) and issubclass(obj, (list, List))):
            return TypeInfo(
                type_name="list",
                original_type=list,
                category=TypeCategory.COLLECTION,
                is_container=True,
                element_type="any"
            )
        elif isinstance(obj, (dict, Dict)) or \
             (isinstance(obj, type) and issubclass(obj, dict)):
            return TypeInfo(
                type_name="dict",
                original_type=dict,
                category=TypeCategory.COLLECTION,
                is_container=True,
                key_type="str",
                element_type="any"
            )
        else:  # tuple
            return TypeInfo(
                type_name="tuple",
                original_type=tuple,
                category=TypeCategory.COLLECTION,
                is_container=True,
                element_type="any"
            )

class DataclassHandler(TypeHandler):
    """Dataclass 处理器"""
    
    def can_handle(self, obj: Any) -> bool:
        return hasattr(obj, '__dataclass_fields__') or \
               (isinstance(obj, type) and hasattr(obj, '__dataclass_fields__'))
    
    def get_type_info(self, obj: Any) -> TypeInfo:
        type_cls = obj if isinstance(obj, type) else obj.__class__
        return TypeInfo(
            type_name=type_cls.__name__,
            original_type=type_cls,
            category=TypeCategory.STRUCTURE,
            is_container=False
        )
    
    def get_paths(self, obj: Any, parent_path: str = "") -> List[Tuple[str, str, PathType, str]]:
        """获取所有可能的路径"""
        paths = []
        type_cls = obj if isinstance(obj, type) else obj.__class__
        
        # 添加根路径
        paths.append((parent_path, type_cls.__name__, PathType.REVERSIBLE, "dot"))
        
        # 获取字段信息
        fields = type_cls.__dataclass_fields__
        for field_name, field in fields.items():
            current_path = f"{parent_path}.{field_name}" if parent_path else field_name
            field_type = field.type
            type_name = getattr(field_type, '__name__', str(field_type))
            paths.append((current_path, type_name, PathType.REVERSIBLE, "dot"))
                
        return paths
    
    def get_nested_fields(self, obj: Any) -> List[Tuple[str, Any]]:
        """获取嵌套字段"""
        nested_fields = []
        type_cls = obj if isinstance(obj, type) else obj.__class__
        
        for field_name, field in type_cls.__dataclass_fields__.items():
            field_type = field.type
            if hasattr(field_type, "__dataclass_fields__") or \
               (isinstance(field_type, type) and hasattr(field_type, "__dataclass_fields__")):
                nested_fields.append((field_name, field_type))
                
        return nested_fields
    
    def extract_value(self, obj: Any, segment: PathSegment) -> Any:
        """提取指定路径段的值"""
        if segment.type == SegmentType.ATTRIBUTE:
            return getattr(obj, segment.value)
        raise ValueError(f"Dataclass 不支持 {segment.type} 访问")
    
    def parse_segment(self, path: str) -> Optional[PathSegment]:
        """解析路径段"""
        if path.isidentifier():
            return PathSegment(
                type=SegmentType.ATTRIBUTE,
                value=path,
                original=path,
                access_method="dot"
            )
        return None

class PydanticHandler(TypeHandler):
    """Pydantic 模型处理器"""
    
    def can_handle(self, obj: Any) -> bool:
        return isinstance(obj, BaseModel) or \
               (isinstance(obj, type) and issubclass(obj, BaseModel))
    
    def get_type_info(self, obj: Any) -> TypeInfo:
        type_cls = obj if isinstance(obj, type) else obj.__class__
        return TypeInfo(
            type_name=type_cls.__name__,
            original_type=type_cls,
            category=TypeCategory.STRUCTURE,
            is_container=False
        )
    
    def get_paths(self, obj: Any, parent_path: str = "") -> List[Tuple[str, str, PathType, str]]:
        """获取所有可能的路径"""
        paths = []
        type_cls = obj if isinstance(obj, type) else obj.__class__
        
        # 添加根路径
        paths.append((parent_path, type_cls.__name__, PathType.REVERSIBLE, "dot"))
        
        # 获取字段信息
        model_fields = type_cls.model_fields if hasattr(type_cls, 'model_fields') else type_cls.__fields__
        for field_name, field in model_fields.items():
            current_path = f"{parent_path}.{field_name}" if parent_path else field_name
            field_type = field.annotation if hasattr(field, 'annotation') else field.type_
            type_name = getattr(field_type, '__name__', str(field_type))
            paths.append((current_path, type_name, PathType.REVERSIBLE, "dot"))
                
        return paths
    
    def get_nested_fields(self, obj: Any) -> List[Tuple[str, Any]]:
        """获取嵌套字段"""
        nested_fields = []
        type_cls = obj if isinstance(obj, type) else obj.__class__
        model_fields = type_cls.model_fields if hasattr(type_cls, 'model_fields') else type_cls.__fields__
        
        for field_name, field in model_fields.items():
            field_type = field.annotation if hasattr(field, 'annotation') else field.type_
            if isinstance(field_type, type) and issubclass(field_type, BaseModel):
                nested_fields.append((field_name, field_type))
                
        return nested_fields
    
    def extract_value(self, obj: Any, segment: PathSegment) -> Any:
        """提取指定路径段的值"""
        if segment.type == SegmentType.ATTRIBUTE:
            return getattr(obj, segment.value)
        raise ValueError(f"Pydantic 模型不支持 {segment.type} 访问")
    
    def parse_segment(self, path: str) -> Optional[PathSegment]:
        """解析路径段"""
        if path.isidentifier():
            return PathSegment(
                type=SegmentType.ATTRIBUTE,
                value=path,
                original=path,
                access_method="dot"
            )
        return None
