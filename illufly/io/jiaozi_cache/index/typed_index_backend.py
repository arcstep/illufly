"""类型安全的索引后端基类"""

from typing import Dict, Type, Any, Optional
import logging
from datetime import datetime
from .index_backend import IndexBackend
from enum import Enum

class IndexError(Exception):
    """索引操作异常基类"""
    pass

class TypeMismatchError(IndexError):
    """类型不匹配异常"""
    def __init__(self, field: str, value: Any, expected_type: Type, message: str = None):
        self.field = field
        self.value = value
        self.expected_type = expected_type
        self.message = message or f"字段 {field} 的值 {value} 无法转换为 {expected_type.__name__}"
        super().__init__(self.message)

class InvalidValueError(IndexError):
    """无效值异常"""
    pass

class ErrorHandling(Enum):
    """错误处理策略"""
    STRICT = "strict"      # 严格模式：类型不匹配时抛出异常
    WARNING = "warning"    # 警告模式：记录警告并跳过
    COERCE = "coerce"     # 强制模式：尝试强制转换


class TypedIndexBackend(IndexBackend):
    """提供类型安全和错误处理的索引后端"""
    
    def __init__(self,
                 field_types: Dict[str, Type] = None,
                 error_handling: ErrorHandling = ErrorHandling.WARNING,
                 logger: Optional[logging.Logger] = None):
        self._field_types = field_types or {}
        self._error_handling = error_handling
        self.logger = logger or logging.getLogger(__name__)

    def _convert_value(self, field: str, value: Any) -> Any:
        """转换值到指定类型"""
        if value is None:
            return None
            
        field_type = self._field_types[field]
        self.logger.debug(f"尝试转换: field={field}, value={value}, type={type(value)}, target_type={field_type}")
        
        # 如果已经是正确类型，直接返回
        if isinstance(value, field_type):
            self.logger.debug("值已经是目标类型")
            return value
            
        try:
            # 特殊处理 datetime
            if field_type == datetime and isinstance(value, str):
                try:
                    return datetime.fromisoformat(value)
                except ValueError as e:
                    if self._error_handling == ErrorHandling.STRICT:
                        raise TypeMismatchError(field, value, field_type) from e
                    self.logger.warning(f"日期时间格式错误: {e}")
                    return None
                    
            # 数值类型的特殊处理
            if field_type in (int, float):
                try:
                    # 先尝试转换为浮点数
                    if isinstance(value, str):
                        float_val = float(value)
                    elif isinstance(value, (int, float)):
                        float_val = float(value)
                    else:
                        float_val = float(str(value))
                    
                    # 整数类型的特殊处理
                    if field_type == int:
                        if float_val.is_integer() or self._error_handling == ErrorHandling.COERCE:
                            return int(float_val)
                        elif self._error_handling == ErrorHandling.STRICT:
                            raise TypeMismatchError(field, value, field_type, 
                                message=f"值 {value} 不是整数")
                        return None
                    
                    # 浮点数类型
                    return float_val
                    
                except (ValueError, TypeError) as e:
                    if self._error_handling == ErrorHandling.STRICT:
                        raise TypeMismatchError(field, value, field_type) from e
                    self.logger.warning(f"数值转换失败: {e}")
                    return None
            
            # 在严格模式下，不允许其他类型转换
            if self._error_handling == ErrorHandling.STRICT:
                raise TypeMismatchError(field, value, field_type,
                    message=f"严格模式下不允许从 {type(value).__name__} 转换为 {field_type.__name__}")
            
            # 非严格模式下的其他类型转换
            try:
                if field_type in (str, bool):
                    return field_type(value)
                self.logger.warning(f"不支持的类型转换: {type(value)} -> {field_type}")
                return None
                    
            except Exception as e:
                self.logger.warning(f"类型转换异常: {e}")
                return None
                
        except Exception as e:
            if self._error_handling == ErrorHandling.STRICT:
                raise TypeMismatchError(field, value, field_type) from e
            self.logger.warning(f"类型转换异常: {e}")
            return None

    def _validate_value(self, field: str, value: Any) -> bool:
        """验证值的类型是否正确"""
        if value is None:
            return True
            
        if isinstance(value, (list, tuple, set)):
            self.logger.debug(f"验证列表值: field={field}, value={value}, type={type(value)}")
            invalid_items = []
            for item in value:
                self.logger.debug(f"检查列表元素: item={item}, type={type(item)}")
                converted = self._convert_value(field, item)
                self.logger.debug(f"转换结果: converted={converted}")
                if converted is None:
                    invalid_items.append(item)
            
            if invalid_items:
                self.logger.debug(f"发现无效元素: {invalid_items}")
                if self._error_handling == ErrorHandling.STRICT:
                    self.logger.debug("严格模式下抛出异常")
                    raise TypeMismatchError(
                        field, 
                        invalid_items, 
                        self._field_types[field],
                        message=f"列表中包含无效类型的元素: {invalid_items}"
                    )
                return False
            return True
        
        converted = self._convert_value(field, value)
        if converted is None and self._error_handling == ErrorHandling.STRICT:
            self.logger.debug(f"单值转换失败: field={field}, value={value}, type={type(value)}")
            raise TypeMismatchError(field, value, self._field_types[field])
        return converted is not None

    def has_index(self, field: str) -> bool:
        """检查索引是否存在"""
        return field in self._field_types