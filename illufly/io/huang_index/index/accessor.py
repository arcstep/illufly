from typing import Any, Protocol, Type, Dict, Tuple, List, Union
from abc import abstractmethod
from pydantic import BaseModel
from collections.abc import Mapping, Sequence
from dataclasses import is_dataclass
import logging

from .path_parser import PathParser, PathSegment, SegmentType

logger = logging.getLogger(__name__)

class ValueAccessor(Protocol):
    """值访问器协议"""
    @abstractmethod
    def get_field_value(self, obj: Any, path_segments: Tuple[PathSegment, ...]) -> Any:
        """根据路径段序列获取值"""
        raise NotImplementedError
    
    @abstractmethod
    def get_type(self) -> Type:
        """获取支持的值类型"""
        raise NotImplementedError
    
    def can_handle(self, value: Any) -> bool:
        """检查是否可以处理特定值"""
        return isinstance(value, self.get_type())

class SequenceAccessor(ValueAccessor):
    """序列类型访问器（支持所有类似列表的类型）"""
    def get_field_value(self, obj: Sequence, path_segments: Tuple[PathSegment, ...]) -> Any:
        if not path_segments:
            return obj
            
        segment = path_segments[0]
        if segment.type != SegmentType.SEQUENCE:
            return None
            
        try:
            index = int(segment.value)
            if not (0 <= index < len(obj)):
                return None
            value = obj[index]
            return value if len(path_segments) == 1 else None
        except (IndexError, ValueError):
            return None
    
    def get_type(self) -> Type:
        return Sequence
    
    def can_handle(self, value: Any) -> bool:
        return isinstance(value, Sequence) and not isinstance(value, (str, bytes))

class MappingAccessor(ValueAccessor):
    """映射类型访问器（支持所有类似字典的类型）"""
    def get_field_value(self, obj: Mapping, path_segments: Tuple[PathSegment, ...]) -> Any:
        if not path_segments:
            return obj
            
        segment = path_segments[0]
        logger.info(f"MappingAccessor: 处理对象 {obj}, 路径段 {segment.type.name}:{segment.value}")
        
        try:
            if segment.type == SegmentType.MAPPING:
                value = obj[segment.value]
                logger.info(f"MappingAccessor: 获取到值 {value}")
                if len(path_segments) > 1:
                    # 如果还有后续路径段，继续处理
                    return self.get_field_value(value, path_segments[1:])
                return value
            else:
                logger.info(f"MappingAccessor: 段类型不匹配，期望 MAPPING，实际 {segment.type.name}")
                return None
        except (KeyError, TypeError) as e:
            logger.info(f"MappingAccessor: 访问失败 - {str(e)}")
            return None
    
    def get_type(self) -> Type:
        return Mapping

class ModelAccessor(ValueAccessor):
    """Pydantic模型访问器"""
    def get_field_value(self, obj: BaseModel, path_segments: Tuple[PathSegment, ...]) -> Any:
        if not path_segments:
            return obj
            
        segment = path_segments[0]
        try:
            if segment.type == SegmentType.ATTRIBUTE:
                value = getattr(obj, segment.value)
            else:
                return None
            return value if len(path_segments) == 1 else None
        except AttributeError:
            return None
    
    def get_type(self) -> Type:
        return BaseModel

class DataclassAccessor(ValueAccessor):
    """Dataclass访问器"""
    def get_field_value(self, obj: Any, path_segments: Tuple[PathSegment, ...]) -> Any:
        if not path_segments or not is_dataclass(obj):
            return obj
            
        segment = path_segments[0]
        try:
            if segment.type == SegmentType.ATTRIBUTE:
                value = getattr(obj, segment.value)
            else:
                return None
            return value if len(path_segments) == 1 else None
        except AttributeError:
            return None
    
    def get_type(self) -> Type:
        return object
    
    def can_handle(self, value: Any) -> bool:
        return is_dataclass(value)

class CompositeAccessor(ValueAccessor):
    """组合访问器"""
    def __init__(self):
        self._accessors = [
            DataclassAccessor(),
            ModelAccessor(),
            MappingAccessor(),
            SequenceAccessor()
        ]
    
    def get_field_value(self, obj: Any, path_segments: Tuple[PathSegment, ...]) -> Any:
        if not path_segments:
            return obj
            
        logger.info(f"CompositeAccessor: 处理对象类型 {type(obj)}")
        accessor = next(
            (acc for acc in self._accessors if acc.can_handle(obj)),
            None
        )
        
        if accessor is None:
            logger.info(f"CompositeAccessor: 未找到合适的访问器处理类型 {type(obj)}")
            return None
            
        logger.info(f"CompositeAccessor: 使用 {accessor.__class__.__name__}")
        value = accessor.get_field_value(obj, path_segments[:1])
        
        if value is None:
            logger.info("CompositeAccessor: 访问返回 None")
            return None
            
        if len(path_segments) > 1:
            logger.info(f"CompositeAccessor: 继续处理剩余路径段 {len(path_segments)-1} 个")
            return self.get_field_value(value, path_segments[1:])
            
        return value
    
    def get_type(self) -> Type:
        return object

class AccessorRegistry:
    """访问器注册表"""
    def __init__(self):
        self._accessors: Dict[Type, ValueAccessor] = {
            dict: DictAccessor(),
            BaseModel: ModelAccessor()
        }
        self._path_parser = PathParser()
    
    def register(self, accessor: ValueAccessor):
        """注册新的访问器"""
        self._accessors[accessor.get_type()] = accessor
    
    def get_accessor(self, value: Any) -> ValueAccessor:
        """获取适合的值访问器"""
        # 1. 直接类型匹配
        if type(value) in self._accessors:
            return self._accessors[type(value)]
            
        # 2. 继承关系匹配
        for base_type, accessor in self._accessors.items():
            if isinstance(value, base_type):
                return accessor
        
        raise ValueError(f"不支持的值类型: {type(value)}")
    
    def get_field_value(self, obj: Any, field_path: str) -> Any:
        """便捷方法：直接获取字段值"""
        accessor = self.get_accessor(obj)
        path_segments = self._path_parser.parse(field_path)
        return accessor.get_field_value(obj, path_segments) 