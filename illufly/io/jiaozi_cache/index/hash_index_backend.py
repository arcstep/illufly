from typing import Dict, Type, Union, Any, List, Optional, Callable
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import json
import logging

from .typed_index_backend import (
    TypedIndexBackend, 
    TypeMismatchError,
    ErrorHandling
)

class HashIndexBackend(TypedIndexBackend):
    """哈希索引实现"""
    def __init__(self, 
                 data_dir: str = None, 
                 filename: str = None,
                 field_types: Dict[str, Type] = None,
                 error_handling: ErrorHandling = ErrorHandling.WARNING,
                 logger: Optional[logging.Logger] = None):
        super().__init__(field_types, error_handling, logger)
        self._indexes = defaultdict(lambda: defaultdict(list))
        self._data_dir = Path(data_dir) if data_dir else None
        self._filename = filename
        
        if data_dir and filename:
            self._load_indexes()

    def _serialize_value(self, value: Any, field_type: Type) -> str:
        """序列化值为字符串"""
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _deserialize_value(self, value_str: str, field: str) -> Any:
        """反序列化字符串值"""
        field_type = self._field_types[field]
        try:
            if field_type == datetime:
                return datetime.fromisoformat(value_str)
            return field_type(value_str)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"值 {value_str} 无法转换为 {field_type.__name__}: {e}")
            return value_str

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引"""
        try:
            # 先验证所有值
            for field in self._field_types:
                value = getattr(data, field, None) if hasattr(data, field) else data.get(field)
                if not self._validate_value(field, value):
                    continue
            
            # 验证通过后执行更新
            self.remove_from_index(owner_id)
            
            for field in self._field_types:
                value = getattr(data, field, None) if hasattr(data, field) else data.get(field)
                if value is None:
                    continue
                    
                if isinstance(value, (list, tuple, set)):
                    for item in value:
                        converted = self._convert_value(field, item)
                        if converted is not None:
                            self._add_to_index(field, converted, owner_id)
                else:
                    converted = self._convert_value(field, value)
                    if converted is not None:
                        self._add_to_index(field, converted, owner_id)
                
            self._save_indexes()
            
        except Exception as e:
            self.remove_from_index(owner_id)
            self._save_indexes()
            if isinstance(e, TypeMismatchError):
                raise
            raise RuntimeError(f"索引更新失败: {e}")

    def _add_to_index(self, field: str, value: Any, owner_id: str) -> None:
        """添加索引"""
        value_key = self._serialize_value(value, self._field_types[field])
        if owner_id not in self._indexes[field][value_key]:
            self._indexes[field][value_key].append(owner_id)

    def find_with_index(self, field: str, value: Any) -> List[str]:
        """查找索引"""
        if not self.has_index(field):
            self.logger.warning(f"索引 {field} 不存在")
            return []
            
        try:
            field_type = self._field_types[field]
            typed_value = field_type(value) if not isinstance(value, field_type) else value
            value_key = self._serialize_value(typed_value, field_type)
            return self._indexes[field][value_key]
        except (ValueError, TypeError) as e:
            self.logger.warning(f"查询值 {value} 无法转换为 {field_type.__name__}: {e}")
            return []

    def _save_indexes(self) -> None:
        """保存索引"""
        index_path = self._get_index_path()
        if not index_path:
            return

        index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                'types': {field: t.__name__ for field, t in self._field_types.items()},
                'indexes': dict(self._indexes)
            }
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存索引失败: {e}")

    def _load_indexes(self) -> None:
        """加载索引"""
        index_path = self._get_index_path()
        if not index_path or not index_path.exists():
            return

        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                type_map = {
                    'str': str,
                    'int': int,
                    'float': float,
                    'bool': bool,
                    'datetime': datetime
                }
                
                for field, type_name in data.get('types', {}).items():
                    self._field_types[field] = type_map.get(type_name, str)
                
                self._indexes = defaultdict(lambda: defaultdict(list))
                for field, field_index in data.get('indexes', {}).items():
                    for value, owner_ids in field_index.items():
                        self._indexes[field][value] = owner_ids
        except Exception as e:
            self.logger.error(f"加载索引失败: {e}")
            self._indexes = defaultdict(lambda: defaultdict(list))

    def remove_from_index(self, owner_id: str) -> None:
        """删除索引"""
        for field_index in self._indexes.values():
            empty_keys = []
            for value_key, owner_ids in field_index.items():
                if owner_id in owner_ids:
                    owner_ids.remove(owner_id)
                    if not owner_ids:
                        empty_keys.append(value_key)
            
            for key in empty_keys:
                field_index.pop(key)
        
        self._save_indexes()

    def _get_index_path(self) -> Optional[Path]:
        """获取索引文件路径"""
        if not (self._data_dir and self._filename):
            return None
        return self._data_dir / ".indexes" / self._filename

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建索引"""
        self._indexes = defaultdict(lambda: defaultdict(list))
        
        data = data_iterator()
        for owner_id, item in data:
            self.update_index(item, owner_id)
        
        self._save_indexes()
        self.logger.info(f"索引重建完成,共处理 {len(data)} 条记录")

