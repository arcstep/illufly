from datetime import datetime, date, time
from decimal import Decimal
from uuid import UUID
from pathlib import Path
from typing import Any, Dict, Type, Callable
import logging

logger = logging.getLogger(__name__)

class TypeConverter:
    """类型转换器"""
    
    def __init__(self):
        self._converters: Dict[str, Callable] = {
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'datetime': self._to_datetime,
            'date': self._to_date,
            'time': self._to_time,
            'decimal': Decimal,
            'uuid': UUID,
            'path': Path,
        }
    
    def convert(self, value: Any, target_type: str) -> Any:
        """转换值到目标类型"""
        if target_type not in self._converters:
            raise ValueError(f"不支持的类型转换: {target_type}")
            
        try:
            return self._converters[target_type](value)
        except Exception as e:
            logger.error(f"类型转换失败: {value} -> {target_type}")
            raise TypeError(f"类型转换失败: {str(e)}")
    
    def register_converter(self, type_name: str, converter: Callable) -> None:
        """注册新的类型转换器"""
        self._converters[type_name] = converter
    
    def _to_datetime(self, value: Any) -> datetime:
        """转换为datetime"""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        raise ValueError(f"无法转换为datetime: {value}")
    
    def _to_date(self, value: Any) -> date:
        """转换为date"""
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return date.fromisoformat(value)
        raise ValueError(f"无法转换为date: {value}")
    
    def _to_time(self, value: Any) -> time:
        """转换为time"""
        if isinstance(value, time):
            return value
        if isinstance(value, str):
            return time.fromisoformat(value)
        raise ValueError(f"无法转换为time: {value}") 