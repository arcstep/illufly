from pathlib import Path
from typing import Any, List, Dict, Optional, Callable, Union
from abc import ABC, abstractmethod
from enum import Enum
from collections import defaultdict
from datetime import datetime

import json
import logging

from .index_backend import IndexBackend

class HashIndexBackend(IndexBackend):
    """哈希索引实现"""
    def __init__(self, data_dir: str = None, filename: str = None,
                 index_fields: List[str] = None, logger=None):
        self._indexes = defaultdict(lambda: defaultdict(list))
        self._index_fields = index_fields or []
        self._data_dir = Path(data_dir) if data_dir else None
        self._filename = filename
        self.logger = logger or logging.getLogger(__name__)
        
        if data_dir and filename:
            self._load_indexes()

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引,支持列表值索引"""
        self.remove_from_index(owner_id)
        
        for field in self._index_fields:
            value = getattr(data, field, None) if hasattr(data, field) else data.get(field)
            if value is None:
                continue
                
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    self._add_to_index(field, item, owner_id)
            else:
                self._add_to_index(field, value, owner_id)
        
        self._save_indexes()

    def _add_to_index(self, field: str, value: Any, owner_id: str) -> None:
        """添加索引"""
        value_key = str(value)
        if owner_id not in self._indexes[field][value_key]:
            self._indexes[field][value_key].append(owner_id)

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

    def find_with_index(self, field: str, value: Any) -> List[str]:
        """查找索引"""
        if not self.has_index(field):
            self.logger.warning(f"索引 {field} 不存在")
            return []
        return self._indexes[field][str(value)]

    def has_index(self, field: str) -> bool:
        """检查索引是否存在"""
        if not self._indexes and self._data_dir and self._filename:
            self._load_indexes()
        return field in self._index_fields

    def _get_index_path(self) -> Optional[Path]:
        """获取索引文件路径"""
        if not (self._data_dir and self._filename):
            return None
        return self._data_dir / ".indexes" / self._filename

    def _load_indexes(self) -> None:
        """加载索引"""
        index_path = self._get_index_path()
        if not index_path or not index_path.exists():
            return

        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                self._indexes = defaultdict(lambda: defaultdict(list))
                for field, field_index in json.load(f).items():
                    for value, owner_ids in field_index.items():
                        self._indexes[field][value] = owner_ids
        except Exception as e:
            self.logger.error(f"加载索引失败: {e}")
            self._indexes = defaultdict(lambda: defaultdict(list))

    def _save_indexes(self) -> None:
        """保存索引"""
        index_path = self._get_index_path()
        if not index_path:
            return

        index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(dict(self._indexes), f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存索引失败: {e}")

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建索引"""
        self._indexes = defaultdict(lambda: defaultdict(list))
        
        data = data_iterator()
        for owner_id, item in data:
            self.update_index(item, owner_id)
        
        self._save_indexes()
        self.logger.info(f"索引重建完成,共处理 {len(data)} 条记录")

