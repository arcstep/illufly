from ..base_rocksdb import BaseRocksDB
from typing import Any, Iterator, Optional, Dict, Tuple
from rocksdict import Rdict, Options, WriteBatch
import logging

class IndexedRocksDB(BaseRocksDB):
    """支持索引功能的RocksDB
    
    扩展基础的BaseRocksDB，提供索引相关的功能：
    1. 索引定义和管理
    2. 索引的增删改查
    3. 基于索引的查询和迭代
    4. 支持多列族操作
    
    Examples:
        with IndexedRocksDB("path/to/db") as db:
            # 定义索引
            db.define_index("age_idx", "age")
            
            # 基本操作（自动更新索引）
            db.put_with_index("user:1", {"age": 25, "name": "Alice"})
            
            # 使用指定列族
            users_cf = db.get_column_family("users")
            db.put_with_index("user:2", user_data, users_cf)
            
            # 批量操作
            with db.batch_write() as batch:
                db.put_with_index("user:3", user_data, batch)
    """
    
    def __init__(
        self,
        path: str,
        options: Optional[Options] = None,
        forward_index_cf_name: str = "_idx_forward",
        reverse_index_cf_name: str = "_idx_reverse",
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__(path, options, logger=logger)
        self._index_defs: Dict[str, str] = {}
        
        # 确保索引列族存在
        self._ensure_index_column_families(forward_index_cf_name, reverse_index_cf_name)
        
        # 获取索引列族和句柄
        self._forward_cf = self.get_column_family(forward_index_cf_name)
        self._reverse_cf = self.get_column_family(reverse_index_cf_name)
        self._forward_handle = self.get_column_family_handle(forward_index_cf_name)
        self._reverse_handle = self.get_column_family_handle(reverse_index_cf_name)
    
    def _ensure_index_column_families(self, forward_name: str, reverse_name: str) -> None:
        """确保索引列族存在"""
        existing_cfs = self.list_column_families(self.path)
        if forward_name not in existing_cfs:
            self.create_column_family(forward_name)
        if reverse_name not in existing_cfs:
            self.create_column_family(reverse_name)
    
    def define_index(self, name: str, field_path: str) -> None:
        """定义新的索引"""
        self._index_defs[name] = field_path
    
    def put_with_index(self, key: Any, value: Any, rdict: Optional[Rdict] = None) -> None:
        """写入数据并更新索引
        
        Args:
            key: 数据键
            value: 要写入的值
            rdict: 可选的Rdict实例（如批处理器、列族等）
        """
        try:
            old_value = self[key]
        except KeyError:
            old_value = None
        
        # 写入数据
        self.put(key, value, rdict)
        
        # 更新索引
        if isinstance(rdict, WriteBatch):
            # 如果是批处理，使用同一个批处理器
            self._update_indexes(key, value, old_value, rdict)
        else:
            # 否则创建新的批处理
            with self.batch_write() as batch:
                self._update_indexes(key, value, old_value, batch)
    
    def del_with_index(self, key: Any, rdict: Optional[Rdict] = None) -> None:
        """删除数据并更新索引"""
        old_value = self[key]
        
        # 删除数据
        self.delete(key, rdict)
        
        # 更新索引
        if isinstance(rdict, WriteBatch):
            self._update_indexes(key, None, old_value, rdict)
        else:
            with self.batch_write() as batch:
                self._update_indexes(key, None, old_value, batch)
    
    def _update_indexes(
        self, 
        key: Any, 
        value: Any, 
        old_value: Any,
        batch: WriteBatch
    ) -> None:
        """更新所有相关索引（内部方法）"""
        # 删除旧索引
        if old_value is not None:
            self._remove_indexes(key, old_value, batch)
        # 创建新索引
        if value is not None:
            self._create_indexes(key, value, batch)
    
    def _remove_indexes(self, key: Any, value: Any, batch: WriteBatch) -> None:
        """删除索引（内部方法）"""
        for index_name, field_path in self._index_defs.items():
            index_value = self._get_field_value(value, field_path)
            if index_value is not None:
                # 删除正向索引
                forward_key = f"{index_name}:{index_value}:{key}"
                batch.delete(forward_key, self._forward_handle)
                
                # 删除反向索引
                reverse_key = f"{index_name}:{key}"
                batch.delete(reverse_key, self._reverse_handle)
    
    def _create_indexes(self, key: Any, value: Any, batch: WriteBatch) -> None:
        """创建索引（内部方法）"""
        for index_name, field_path in self._index_defs.items():
            index_value = self._get_field_value(value, field_path)
            if index_value is not None:
                # 创建正向索引 (index_value -> key)
                forward_key = f"{index_name}:{index_value}:{key}"
                batch.put(forward_key, key, self._forward_handle)
                
                # 创建反向索引 (key -> index_value)
                reverse_key = f"{index_name}:{key}"
                batch.put(reverse_key, index_value, self._reverse_handle)
    
    def query_by_index(self, index_name: str, value: Any) -> Iterator[Tuple[Any, Any]]:
        """通过索引查询
        
        Args:
            index_name: 索引名称
            value: 索引值
            
        Returns:
            (key, value) 对的迭代器
        """
        prefix = f"{index_name}:{value}:"
        for forward_key, key in self._forward_cf.items_with_prefix(prefix):
            yield key, self[key]
    
    def iter_by_index(self, index_name: str) -> Iterator[Tuple[Any, Any]]:
        """通过索引迭代所有数据"""
        prefix = f"{index_name}:"
        for forward_key, key in self._forward_cf.items_with_prefix(prefix):
            yield key, self[key]
    
    @staticmethod
    def _get_field_value(obj: Any, field_path: str) -> Any:
        """获取对象中指定路径的字段值（内部方法）"""
        parts = field_path.split('.')
        value = obj
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value 