from pathlib import Path
from typing import Any, List, Dict, Optional, Callable, Union
from abc import ABC, abstractmethod
from enum import Enum
from collections import defaultdict
from datetime import datetime

import json
import logging

from .index_backend import IndexBackend
from .hash_index_backend import HashIndexBackend
from .btree_index_backend import BTreeIndexBackend
from .ops import COMPARE_OPS, RANGE_OPS

class IndexType(Enum):
    """索引类型"""
    HASH = "hash" 
    BTREE = "btree"


class CompositeIndexBackend(IndexBackend):
    """组合索引后端"""
    def __init__(self, data_dir: str = None, filename: str = None,
                 index_config: Dict[str, IndexType] = None,
                 logger: Optional[logging.Logger] = None):
        self._hash_backend = HashIndexBackend(data_dir=data_dir,
                                            filename=filename,
                                            index_fields=[],
                                            logger=logger)
        self._btree_backend = None
        self._index_config = index_config or {}
        self._data_dir = Path(data_dir) if data_dir else None
        self._filename = filename
        self.logger = logger
        
        self._init_indexes()

    def _init_indexes(self) -> None:
        """初始化索引"""
        hash_fields = []
        btree_fields = []
        
        for field, index_type in self._index_config.items():
            if index_type == IndexType.HASH:
                hash_fields.append(field)
            elif index_type == IndexType.BTREE:
                btree_fields.append(field)
                
        self._hash_backend._index_fields = hash_fields
        
        if btree_fields:
            self._btree_backend = BTreeIndexBackend(
                data_dir=self._data_dir,
                filename=f"{self._filename}_btree",
                index_fields=btree_fields,
                logger=self.logger
            )

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引"""
        for field, index_type in self._index_config.items():
            value = self._get_value_by_path(data, field)
            if value is not None:
                if index_type == IndexType.HASH:
                    self._hash_backend.update_index({field: value}, owner_id)
                elif index_type == IndexType.BTREE and self._btree_backend:
                    self._btree_backend.update_index({field: value}, owner_id)

    def find_with_index(self, field: str, value: Any) -> List[str]:
        """查找索引"""
        if field not in self._index_config:
            return []
            
        index_type = self._index_config[field]
        if index_type == IndexType.HASH:
            return self._hash_backend.find_with_index(field, value)
        elif index_type == IndexType.BTREE and self._btree_backend:
            return self._btree_backend.find_with_index(field, value)
        return []

    def has_index(self, field: str) -> bool:
        """检查索引是否存在"""
        return field in self._index_config

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建所有索引"""
        self._hash_backend.rebuild_indexes(data_iterator)
        if self._btree_backend:
            self._btree_backend.rebuild_indexes(data_iterator)

    def remove_from_index(self, owner_id: str) -> None:
        """从索引中删除"""
        self._hash_backend.remove_from_index(owner_id)
        if self._btree_backend:
            self._btree_backend.remove_from_index(owner_id)

    def query(self, field: str, op: str, *values: Any) -> List[str]:
        """统一的查询接口
        
        Args:
            field: 字段名
            op: 操作符 (==, !=, >=, <=, >, <, [], (), [), (], contains)
            values: 查询值
            
        Returns:
            匹配的 owner_id 列表
            
        Raises:
            ValueError: 当操作符与索引类型不匹配时
        """
        if field not in self._index_config:
            return []
            
        index_type = self._index_config[field]
        
        # 哈希索引只支持等值查询和集合操作
        if index_type == IndexType.HASH:
            if op not in ("==", "!=", "contains"):
                raise ValueError(f"哈希索引不支持 {op} 操作")
                
            if op == "contains":
                return self._hash_backend.find_with_index(field, values[0])
            else:
                results = self._hash_backend.find_with_index(field, values[0])
                return [] if op == "!=" else results
                
        # B树索引支持比较和区间操作
        elif index_type == IndexType.BTREE and self._btree_backend:
            if op in COMPARE_OPS:
                return self._btree_backend.query(field, op, values[0])
            elif op in RANGE_OPS:
                if len(values) != 2:
                    raise ValueError(f"区间操作符 {op} 需要两个值")
                return self._btree_backend.query(field, op, values[0], values[1])
            else:
                raise ValueError(f"B树索引不支持 {op} 操作")
                
        return []

    def clear(self) -> None:
        """清除所有索引"""
        self._hash_backend = HashIndexBackend(
            data_dir=self._data_dir,
            filename=self._filename,
            index_fields=[],
            logger=self.logger
        )
        if self._btree_backend:
            self._btree_backend = BTreeIndexBackend(
                data_dir=self._data_dir,
                filename=f"{self._filename}_btree",
                index_fields=[],
                logger=self.logger
            )
        self._init_indexes()

