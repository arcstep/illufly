from typing import Any, Protocol, Type, Dict, Tuple, List, Union, Optional
from abc import abstractmethod
from pydantic import BaseModel
from collections.abc import Mapping, Sequence
from dataclasses import is_dataclass, fields
import logging
import inspect

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
    
    @abstractmethod
    def validate_path(self, value_type: Type, path_segments: Tuple[PathSegment, ...]) -> Optional[str]:
        """验证路径是否可以访问指定类型
        
        Args:
            value_type: 要验证的值类型
            path_segments: 路径段序列
            
        Returns:
            Optional[str]: 如果路径无效，返回错误信息；如果有效，返回 None
        """
        raise NotImplementedError
    
    def can_handle(self, value: Any) -> bool:
        """检查是否可以处理特定值或类型
        
        Args:
            value: 要检查的值或类型
            
        Returns:
            bool: 如果可以处理该值或类型则返回 True
        """
        if isinstance(value, type):
            # 处理类型
            return issubclass(value, self.get_type())
        else:
            # 处理实例
            return isinstance(value, self.get_type())

class SequenceAccessor(ValueAccessor):
    """序列类型访问器（支持所有类似列表的类型）"""
    def __init__(self, logger: Optional[logging.Logger] = None):
        self._logger = logger or logging.getLogger(__name__)
        
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
        """检查是否可以处理序列类型"""
        
        # 处理泛型类型
        if hasattr(value, '__origin__'):
            origin = value.__origin__
            return origin in (list, List)
        
        # 处理普通类型
        if isinstance(value, type):
            return issubclass(value, (list, List)) and not issubclass(value, (str, bytes))
        
        # 处理实例
        return isinstance(value, Sequence) and not isinstance(value, (str, bytes))
    
    def validate_path(self, value_type: Type, path_segments: Tuple[PathSegment, ...]) -> Optional[str]:
        if not path_segments:
            return None
            
        segment = path_segments[0]
        if segment.type != SegmentType.SEQUENCE:
            return f"类型 {value_type.__name__} 不支持 {segment.type.name} 访问"
            
        try:
            index = int(segment.value)
            if index < 0:
                return f"序列索引不能为负数: {index}"
        except ValueError:
            return f"无效的序列索引: {segment.value}"
            
        return None

class MappingAccessor(ValueAccessor):
    """映射类型访问器（支持所有类似字典的类型）"""
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        
    def get_field_value(self, obj: Any, path_segments: Tuple[PathSegment, ...]) -> Any:
        """获取字段值"""
        current = obj
        for segment in path_segments:
            
            # 修改：对于字典类型，直接使用键访问
            if isinstance(current, dict):
                if segment.type == SegmentType.ATTRIBUTE:
                    try:
                        current = current[segment.value]
                        continue
                    except (KeyError, TypeError):
                        return None
                        
            # 其他类型的处理保持不变
            if segment.type == SegmentType.MAPPING:
                if not isinstance(current, Mapping):
                    return None
                try:
                    current = current[segment.value]
                except (KeyError, TypeError):
                    return None
            elif segment.type == SegmentType.ATTRIBUTE:
                try:
                    current = getattr(current, segment.value)
                except (AttributeError, TypeError):
                    return None
                    
        return current
    
    def get_type(self) -> Type:
        return Mapping
    
    def validate_path(self, value_type: Type, path_segments: Tuple[PathSegment, ...]) -> Optional[str]:
        if not path_segments:
            return None
            
        segment = path_segments[0]
        # 字典类型支持 MAPPING 和 ATTRIBUTE 访问
        if segment.type not in (SegmentType.MAPPING, SegmentType.ATTRIBUTE):
            return f"类型 {value_type.__name__} 不支持 {segment.type.name} 访问"
            
        return None
    
    def can_handle(self, value: Any) -> bool:
        """检查是否可以处理映射类型"""
        
        # 处理泛型类型
        if hasattr(value, '__origin__'):
            origin = value.__origin__
            return origin in (dict, Dict)
            
        # 处理普通类型
        if isinstance(value, type):
            return issubclass(value, (dict, Dict))
            
        # 处理实例
        return isinstance(value, Mapping)

class ModelAccessor(ValueAccessor):
    """Pydantic模型访问器"""
    def __init__(self, logger: Optional[logging.Logger] = None):
        self._logger = logger or logging.getLogger(__name__)
        
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
    
    def validate_path(self, value_type: Type, path_segments: Tuple[PathSegment, ...]) -> Optional[str]:
        if not path_segments:
            return None
            
        segment = path_segments[0]
        if segment.type != SegmentType.ATTRIBUTE:
            return f"Pydantic 模型不支持 {segment.type.name} 访问"
            
        if not issubclass(value_type, BaseModel):
            return f"类型 {value_type.__name__} 不是 Pydantic 模型"
            
        model_fields = value_type.model_fields
        if segment.value not in model_fields:
            return f"模型 {value_type.__name__} 没有字段 '{segment.value}'"
            
        return None

    def can_handle(self, value: Any) -> bool:
        """检查是否可以处理 Pydantic 模型"""
        if isinstance(value, type):
            return issubclass(value, BaseModel)
        return isinstance(value, BaseModel)

class DataclassAccessor(ValueAccessor):
    """Dataclass访问器"""
    def __init__(self, logger: Optional[logging.Logger] = None):
        self._logger = logger or logging.getLogger(__name__)
        
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
        """检查是否可以处理 dataclass"""
        if isinstance(value, type):
            return is_dataclass(value)
        return is_dataclass(value.__class__)
    
    def validate_path(self, value_type: Type, path_segments: Tuple[PathSegment, ...]) -> Optional[str]:
        """验证路径是否可以访问指定的 dataclass 类型
        
        Args:
            value_type: 要验证的值类型
            path_segments: 路径段序列
            
        Returns:
            Optional[str]: 如果路径无效，返回错误信息；如果有效，返回 None
        """
        if not path_segments:
            return None
            
        if not is_dataclass(value_type):
            return f"类型 {value_type.__name__} 不是 dataclass"
            
        segment = path_segments[0]
        if segment.type != SegmentType.ATTRIBUTE:
            return f"Dataclass 不支持 {segment.type.name} 访问"
            
        # 正确导入和使用 fields
        dataclass_fields = {f.name: f for f in fields(value_type)}
        if segment.value not in dataclass_fields:
            return f"Dataclass {value_type.__name__} 没有字段 '{segment.value}'"
            
        return None

class CompositeAccessor(ValueAccessor):
    """组合访问器"""
    def __init__(self, logger: Optional[logging.Logger] = None):
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        # 调整访问器顺序，确保特定类型在前
        self._accessors = [
            SequenceAccessor(),  # 先检查序列类型
            MappingAccessor(),   # 再检查映射类型
            ModelAccessor(),     # 然后是模型类型
            DataclassAccessor()  # 最后是数据类类型
        ]
    
    def get_field_value(self, obj: Any, path_segments: Tuple[PathSegment, ...]) -> Any:
        if not path_segments:
            return obj
            
        accessor = next(
            (acc for acc in self._accessors if acc.can_handle(obj)),
            None
        )
        
        if accessor is None:
            return None
            
        value = accessor.get_field_value(obj, path_segments[:1])
        
        if value is None:
            return None
            
        if len(path_segments) > 1:
            return self.get_field_value(value, path_segments[1:])
            
        return value
    
    def get_type(self) -> Type:
        return object
    
    def validate_path(self, value_type: Type, path_segments: Tuple[PathSegment, ...]) -> Optional[str]:
        """验证路径是否可以访问指定类型"""
        if not path_segments:
            return None
            
        # 找到合适的访问器
        accessor = None
        for acc in self._accessors:
            if acc.can_handle(value_type):
                accessor = acc
                break
        
        if accessor is None:
            error_msg = f"找不到适合类型 {value_type.__name__} 的访问器"
            self._logger.error(error_msg)
            return error_msg
        
        # 验证第一段路径
        error = accessor.validate_path(value_type, path_segments[:1])
        if error:
            self._logger.error(f"路径验证失败: {error}")
            return error
        
        # 如果有更多路径段，递归验证
        if len(path_segments) > 1:            
            try:
                # 获取下一级的类型
                if hasattr(value_type, 'model_fields'):
                    # Pydantic 模型
                    field_name = path_segments[0].value
                    next_type = value_type.model_fields[field_name].annotation
                elif hasattr(value_type, '__origin__') and value_type.__origin__ in (list, List):
                    # 处理列表类型，获取元素类型
                    next_type = value_type.__args__[0]
                elif hasattr(value_type, '__origin__') and value_type.__origin__ in (dict, Dict):
                    # 处理字典类型，获取值类型
                    next_type = value_type.__args__[1]
                elif hasattr(value_type, '__annotations__'):
                    # 普通类的类型注解
                    next_type = get_type_hints(value_type)[path_segments[0].value]
                else:
                    error_msg = f"无法获取 {value_type.__name__} 的类型信息"
                    self._logger.error(error_msg)
                    return error_msg
                    
                return self.validate_path(next_type, path_segments[1:])
                
            except Exception as e:
                error_msg = f"获取下一级类型时出错: {str(e)}"
                self._logger.error(error_msg)
                return error_msg
                
        return None

    def can_handle(self, value: Any) -> bool:
        """检查是否可以处理特定值或类型"""
        
        for accessor in self._accessors:
            can_handle = accessor.can_handle(value)
            
            if can_handle:
                return True
                
        self._logger.warning(f"没有找到合适的访问器处理: {value}")
        if isinstance(value, type) and hasattr(value, '__origin__'):
            self._logger.warning(f"类型信息: origin={value.__origin__}, args={getattr(value, '__args__', None)}")
        return False

class AccessorRegistry:
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._path_parser = PathParser()
        # 只需要一个组合访问器
        self._accessor = CompositeAccessor(self._logger)
        
    def get_field_value(self, obj: Any, field_path: str) -> Any:
        """便捷方法：直接获取字段值"""
        path_segments = self._path_parser.parse(field_path)
        return self._accessor.get_field_value(obj, path_segments) 
    
    def validate_path(self, value_type: Type, field_path: str) -> None:
        """验证字段路径"""
        path_segments = self._path_parser.parse(field_path)
        if error := self._accessor.validate_path(value_type, path_segments):
            raise ValueError(f"无效的访问路径 '{field_path}': {error}")