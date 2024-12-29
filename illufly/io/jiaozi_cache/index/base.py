from typing import Dict, Any, List, Optional, Callable, Type, Union
from pathlib import Path
from collections import defaultdict
import logging

from .index_backend import IndexBackend
from .config import IndexConfig, IndexUpdateStrategy
from .hash_index_backend import HashIndexBackend
from .btree_index_backend import BTreeIndexBackend
from .ops import COMPARE_OPS, RANGE_OPS

class IndexType:
    """索引类型"""
    HASH = "hash"
    BTREE = "btree"

class CompositeIndexBackend(IndexBackend):
    """组合索引后端
    
    特点：
    - 支持多种索引类型组合
    - 自动选择最优索引
    - 统一的查询接口
    - 共享配置和类型约束
    
    存储结构：
    - _hash_indexes: 哈希索引实例字典
    - _btree_indexes: B树索引实例字典
    """
    
    def __init__(self, 
                 field_types: Dict[str, Any] = None,
                 index_types: Dict[str, str] = None,
                 config: Optional[IndexConfig] = None,
                 data_dir: str = None,
                 filename: str = None):
        """初始化组合索引后端
        
        Args:
            field_types: 字段类型约束
            config: 索引配置
            index_types: 字段索引类型映射 {"field": "hash|btree"}
            data_dir: 索引文件存储目录
            filename: 索引文件名前缀
        """
        super().__init__(field_types=field_types, config=config)
        self._index_types = index_types or {}
        self._data_dir = Path(data_dir) if data_dir else None
        self._filename = filename
        
        # 索引实例
        self._hash_indexes = {}
        self._btree_indexes = {}
        
        self._init_indexes()

    def _init_indexes(self) -> None:
        """初始化索引实例"""
        # 为每个子索引创建配置
        sub_config = self._config.model_copy()
        
        # 分类字段并创建索引
        for field, index_type in self._index_types.items():
            if field not in self._field_types:
                self.logger.warning(f"字段 {field} 未定义类型约束")
                continue
                
            field_type = self._field_types[field]
            if index_type == "hash":
                self._hash_indexes[field] = HashIndexBackend(
                    field_types={field: field_type},
                    config=sub_config,
                    data_dir=self._data_dir,
                    filename=f"{self._filename}_hash_{field}" if self._filename else None
                )
            elif index_type == "btree":
                self._btree_indexes[field] = BTreeIndexBackend(
                    field_types={field: field_type},
                    config=sub_config,
                    data_dir=self._data_dir,
                    filename=f"{self._filename}_btree_{field}" if self._filename else None
                )
            else:
                self.logger.warning(f"未知的索引类型: {index_type}")

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新所有索引
        
        Args:
            data: 要索引的数据对象
            owner_id: 数据所有者ID
        """
        try:
            # 更新哈希索引
            for field, index in self._hash_indexes.items():
                value = self._get_value_by_path(data, field)
                if value is not None:
                    index.update_index({field: value}, owner_id)
            
            # 更新B树索引
            for field, index in self._btree_indexes.items():
                value = self._get_value_by_path(data, field)
                if value is not None:
                    index.update_index({field: value}, owner_id)
                    
            self._update_stats("updates")
            
        except Exception as e:
            self.remove_from_index(owner_id)
            raise RuntimeError(f"索引更新失败: {e}")

    def find_with_index(self, field: str, value: Any) -> List[str]:
        """使用索引查找数据
        
        Args:
            field: 索引字段
            value: 查找值
            
        Returns:
            List[str]: 匹配的所有者ID列表
        """
        if field not in self._index_types:
            return []
            
        index_type = self._index_types[field]
        try:
            if index_type == IndexType.HASH:
                result = self._hash_indexes[field].find_with_index(field, value)
            elif index_type == IndexType.BTREE:
                result = self._btree_indexes[field].find_with_index(field, value)
            else:
                return []
                
            self._update_stats("queries")
            return result
            
        except Exception as e:
            self.logger.warning(f"索引查询失败: {e}")
            return []

    def query(self, field: str, op: str, *values: Any) -> List[str]:
        """统一的查询接口
        
        支持的操作符:
        - 比较: ==, !=, >, >=, <, <=
        - 范围: between, not_between
        
        Args:
            field: 索引字段
            op: 操作符
            values: 查询值（一个或两个）
            
        Returns:
            List[str]: 匹配的所有者ID列表
        """
        if field not in self._index_types:
            return []
            
        index_type = self._index_types[field]
        try:
            # 哈希索引只支持等值查询
            if index_type == IndexType.HASH:
                if op not in ("==", "!="):
                    raise ValueError(f"哈希索引不支持 {op} 操作")
                    
                results = self._hash_indexes[field].find_with_index(field, values[0])
                return [] if op == "!=" else results
                
            # B树索引支持所有操作
            elif index_type == IndexType.BTREE:
                btree = self._btree_indexes[field]
                if op in COMPARE_OPS:
                    return btree.find_with_index(field, values[0])
                elif op in RANGE_OPS:
                    if len(values) != 2:
                        raise ValueError(f"区间操作符 {op} 需要两个值")
                    return btree.range_search(field, values[0], values[1])
                    
            self._update_stats("queries")
            
        except Exception as e:
            self.logger.warning(f"查询执行失败: {e}")
            
        return []

    def remove_from_index(self, owner_id: str) -> None:
        """删除指定所有者的所有索引
        
        Args:
            owner_id: 数据所有者ID
        """
        # 从所有索引中删除
        for index in self._hash_indexes.values():
            index.remove_from_index(owner_id)
            
        for index in self._btree_indexes.values():
            index.remove_from_index(owner_id)

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建所有索引
        
        Args:
            data_iterator: 返回(owner_id, data)元组列表的迭代器
        """
        # 重建所有索引
        for index in self._hash_indexes.values():
            index.rebuild_indexes(data_iterator)
            
        for index in self._btree_indexes.values():
            index.rebuild_indexes(data_iterator)
            
        self._stats["last_rebuild"] = True

    def get_index_size(self) -> Dict[str, int]:
        """获取所有索引的大小
        
        Returns:
            Dict[str, int]: 字段到索引大小的映射
        """
        sizes = {}
        for field, index in self._hash_indexes.items():
            sizes[f"{field}(hash)"] = index.get_index_size()
            
        for field, index in self._btree_indexes.items():
            sizes[f"{field}(btree)"] = index.get_index_size()
            
        return sizes

    def get_index_memory_usage(self) -> Dict[str, int]:
        """获取所有索引的内存使用量
        
        Returns:
            Dict[str, int]: 字段到内存使用量(字节)的映射
        """
        memory = {}
        for field, index in self._hash_indexes.items():
            memory[f"{field}(hash)"] = index.get_index_memory_usage()
            
        for field, index in self._btree_indexes.items():
            memory[f"{field}(btree)"] = index.get_index_memory_usage()
            
        return memory

    def has_index(self, field: str) -> bool:
        """检查字段是否已建立索引"""
        return field in self._index_types

