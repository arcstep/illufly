"""类型安全的索引后端基类"""

from typing import Dict, Type, Any, Optional, List
import logging
from datetime import datetime
from .index_backend import IndexBackend
from enum import Enum

class IndexError(Exception):
    """索引操作异常基类"""
    pass

class TypeMismatchError(IndexError):
    """类型不匹配异常

    当字段的值与预期类型不匹配时抛出。
    """
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
    """错误处理策略

    Attributes:
        STRICT: 严格模式，类型不匹配时抛出异常。
        WARNING: 警告模式，记录警告并跳过。
        COERCE: 强制模式，尝试强制转换。
    """
    STRICT = "strict"
    WARNING = "warning"
    COERCE = "coerce"


class TypedIndexBackend(IndexBackend):
    """提供类型安全和错误处理的索引后端

    该类确保在添加数据时，所有字段的类型都符合预期的类型要求。
    支持字符串、数值、时间等原生类型，以及这些类型形成的嵌套字典。

    索引建立策略：
    1. 类型验证：在添加数据时，对每个字段进行类型验证，确保其符合预期类型。
    2. 错误处理策略：
       - 严格模式 (STRICT)：类型不匹配时抛出 TypeMismatchError 异常。
       - 警告模式 (WARNING)：记录警告并跳过不匹配的字段。
       - 强制模式 (COERCE)：尝试将不匹配的类型强制转换为预期类型。
    3. 支持的类型：支持字符串、数值、时间等原生类型，以及这些类型形成的嵌套字典。
    4. 异常处理：在严格模式下，类型不匹配时抛出异常，并提示无法声明索引。

    Attributes:
        _field_types: 字段及其预期类型的字典。
        _error_handling: 错误处理策略。
        logger: 用于记录日志的 Logger 对象。
    """
    
    def __init__(self,
                 field_types: Dict[str, Type] = None,
                 error_handling: ErrorHandling = ErrorHandling.WARNING,
                 logger: Optional[logging.Logger] = None):
        """初始化 TypedIndexBackend

        Args:
            field_types: 指定每个字段的预期类型。
            error_handling: 指定错误处理策略。
            logger: 用于记录日志的 Logger 对象。
        """
        self._field_types = field_types or {}
        self._error_handling = error_handling
        self.logger = logger or logging.getLogger(__name__)

    def add(self, data: Dict[str, Any], owner_id: str) -> None:
        """添加数据并进行类型验证

        在添加数据时，验证每个字段的类型是否符合预期。

        Args:
            data: 包含字段和值的字典。
            owner_id: 数据的所有者标识。

        Raises:
            TypeMismatchError: 如果字段的类型不符合预期，并且错误处理策略是严格模式。
        """
        validated_data = self.update_index(data, owner_id)
        if validated_data:
            super().add(validated_data, owner_id)

    def update_index(self, data: Dict[str, Any], owner_id: str) -> Dict[str, Any]:
        """更新索引，确保类型安全，返回验证后的数据

        Args:
            data: 包含字段和值的字典。
            owner_id: 数据的所有者标识。

        Returns:
            验证后的数据字典。

        Raises:
            TypeMismatchError: 如果字段的类型不符合预期，并且错误处理策略是严格模式。
        """
        validated_data = {}
        
        for field, expected_type in self._field_types.items():
            value = data.get(field)
            
            if value is None:
                continue
            
            if not self._validate_value(field, value):
                if self._error_handling == ErrorHandling.STRICT:
                    raise TypeMismatchError(field, value, expected_type)
                self.logger.warning(f"字段 {field} 的值 {value} 类型不匹配，期望类型为 {expected_type.__name__}")
                continue
            
            validated_data[field] = value
        
        return validated_data

    def _validate_value(self, field: str, value: Any) -> bool:
        """验证值的类型是否正确

        Args:
            field: 字段名称。
            value: 字段的值。

        Returns:
            如果值的类型正确，返回 True；否则返回 False。

        Raises:
            TypeMismatchError: 如果字段的类型不符合预期，并且错误处理策略是严格模式。
        """
        if not self._is_valid_key(value):
            if self._error_handling == ErrorHandling.STRICT:
                raise TypeMismatchError(field, value, "普通类型或字典嵌套")
            return False
        return True

    def _is_valid_key(self, key: Any) -> bool:
        """检查键是否为有效类型"""
        if isinstance(key, (str, int, float, bool, type(None))):
            return True
        if isinstance(key, dict):
            return all(self._is_valid_key(k) and self._is_valid_key(v) for k, v in key.items())
        return False

    def _convert_value(self, field: str, value: Any, target_type: Type) -> Any:
        """转换值到目标类型"""
        self.logger.debug(f"尝试转换: field={field}, value={value}, type={type(value)}, target_type={target_type}")
        
        # 如果已经是目标类型，直接返回
        if isinstance(value, target_type):
            self.logger.debug("值已经是目标类型")
            return value
            
        try:
            # 特殊处理 datetime
            if target_type == datetime and isinstance(value, str):
                return datetime.fromisoformat(value)
                
            # 数值类型的特殊处理
            if target_type in (int, float):
                try:
                    # 字符串转数值
                    if isinstance(value, str):
                        value = float(value)
                    
                    # 整数类型的特殊处理
                    if target_type == int:
                        if isinstance(value, (int, float)):
                            if float(value).is_integer():
                                return int(value)
                            elif self._error_handling == ErrorHandling.COERCE:
                                return int(float(value))  # 强制转换浮点数为整数
                        if self._error_handling == ErrorHandling.STRICT:
                            raise TypeMismatchError(field, value, target_type)
                        return None
                    
                    # 浮点数类型
                    if isinstance(value, (int, float)):
                        return float(value)
                    
                except (ValueError, TypeError) as e:
                    if self._error_handling == ErrorHandling.STRICT:
                        raise TypeMismatchError(field, value, target_type)
                    self.logger.warning(f"数值转换失败: {e}")
                    return None
                
            # 其他类型的转换
            if self._error_handling == ErrorHandling.STRICT:
                raise TypeMismatchError(field, value, target_type)
            try:
                return target_type(value)
            except (ValueError, TypeError) as e:
                self.logger.warning(f"类型转换失败: {e}")
                return None
            
        except Exception as e:
            if self._error_handling == ErrorHandling.STRICT:
                raise TypeMismatchError(field, value, target_type)
            self.logger.warning(f"类型转换异常: {e}")
            return None

    def has_index(self, field: str) -> bool:
        """检查索引是否存在"""
        return field in self._field_types

    def _validate_list_value(self, field: str, value: List[Any]) -> List[Any]:
        """验证列表值的类型一致性并进行必要的转换"""
        if not value:  # 空列表直接返回
            return value

        # 获取第一个元素的类型作为基准类型
        first_type = type(value[0])
        
        # 检查所有元素的类型
        converted_values = []
        for item in value:
            current_type = type(item)
            self.logger.debug(f"检查列表元素: item={item}, type={current_type}")
            
            # 如果类型不一致且在严格模式下，抛出异常
            if current_type != first_type and self._error_handling == ErrorHandling.STRICT:
                raise TypeMismatchError(
                    field, 
                    item, 
                    first_type,
                    f"列表中的元素类型不一致: 期望 {first_type}, 实际 {current_type}"
                )
                
            # 尝试转换到目标类型
            target_type = self._field_types.get(field, first_type)
            try:
                converted = self._convert_value(field, item, target_type)
                if converted is not None:
                    converted_values.append(converted)
                elif self._error_handling == ErrorHandling.STRICT:
                    raise TypeMismatchError(field, item, target_type)
            except (ValueError, TypeError) as e:
                if self._error_handling == ErrorHandling.STRICT:
                    raise TypeMismatchError(field, item, target_type)
                self.logger.warning(f"列表元素转换失败: {e}")

        return converted_values if converted_values else None

    def _get_target_type(self, field: str, value: Any) -> Type:
        """获取字段的目标类型"""
        # 如果是列表，返回第一个元素的类型
        if isinstance(value, list):
            return type(value[0]) if value else str
        return type(value)