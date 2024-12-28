from pathlib import Path
from typing import Any, List, Dict, Optional, Callable, Union
from abc import ABC, abstractmethod
from enum import Enum
from collections import defaultdict
from datetime import datetime

import json
import logging

# 单值比较操作符
COMPARE_OPS = {
    "==": lambda x, y: x == y,
    "!=": lambda x, y: x != y,
    ">=": lambda x, y: x >= y,
    "<=": lambda x, y: x <= y,
    ">": lambda x, y: x > y,
    "<": lambda x, y: x < y
}

# 区间比较操作符
RANGE_OPS = {
    "[]": lambda x, start, end: start <= x <= end,  # 闭区间
    "()": lambda x, start, end: start < x < end,    # 开区间
    "[)": lambda x, start, end: start <= x < end,   # 左闭右开
    "(]": lambda x, start, end: start < x <= end    # 左开右闭
}

class IndexType(Enum):
    """索引类型"""
    HASH = "hash" 
    BTREE = "btree"

class IndexBackend(ABC):
    """索引后端基类"""
    @abstractmethod
    def update_index(self, data: Any, owner_id: str) -> None:
        pass

    @abstractmethod 
    def remove_from_index(self, owner_id: str) -> None:
        pass

    @abstractmethod
    def find_with_index(self, field: str, value: Any) -> List[str]:
        pass
    
    @abstractmethod
    def has_index(self, field: str) -> bool:
        pass
    
    @abstractmethod
    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        pass

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

class BTreeNode:
    """B树节点"""
    def __init__(self, leaf: bool = False):
        self.leaf = leaf
        self.keys: List[Any] = []
        self.values: Dict[Any, List[str]] = {}
        self.children: List['BTreeNode'] = []

    def is_full(self, order: int) -> bool:
        return len(self.keys) >= 2 * order - 1

class BTreeIndex:
    """B树索引实现"""
    def __init__(self, order: int = 4):
        self._tree = BTreeNode(leaf=True)
        self._order = order
    
    def add(self, value: Any, owner_id: str) -> None:
        if self._tree.is_full(self._order):
            new_root = BTreeNode(leaf=False)
            new_root.children.append(self._tree)
            self._split_child(new_root, 0)
            self._tree = new_root
        self._insert_non_full(self._tree, value, owner_id)
    
    def remove(self, owner_id: str) -> None:
        self._remove_recursive(self._tree, owner_id)
    
    def search(self, value: Any) -> List[str]:
        return self._search_recursive(self._tree, value)
    
    def range_search(self, start: Any, end: Any) -> List[str]:
        result = []
        self._range_search_recursive(self._tree, start, end, result)
        return result
    
    def save(self, path: Path) -> None:
        data = self._serialize_tree(self._tree)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    
    def load(self, path: Path) -> None:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._tree = self._deserialize_tree(data)

    def _split_child(self, parent: BTreeNode, index: int) -> None:
        order = self._order
        child = parent.children[index]
        new_node = BTreeNode(leaf=child.leaf)
        
        mid_key = child.keys[order - 1]
        parent.keys.insert(index, mid_key)
        parent.values[mid_key] = child.values[mid_key]
        
        new_node.keys = child.keys[order:]
        child.keys = child.keys[:order - 1]
        
        for key in new_node.keys:
            new_node.values[key] = child.values[key]
            del child.values[key]
        
        if not child.leaf:
            new_node.children = child.children[order:]
            child.children = child.children[:order]
        
        parent.children.insert(index + 1, new_node)

    def _insert_non_full(self, node: BTreeNode, key: Any, owner_id: str) -> None:
        i = len(node.keys) - 1
        
        if node.leaf:
            while i >= 0 and key < node.keys[i]:
                i -= 1
            i += 1
            
            if i < len(node.keys) and key == node.keys[i]:
                if owner_id not in node.values[key]:
                    node.values[key].append(owner_id)
            else:
                node.keys.insert(i, key)
                node.values[key] = [owner_id]
        else:
            while i >= 0 and key < node.keys[i]:
                i -= 1
            i += 1
            
            if node.children[i].is_full(self._order):
                self._split_child(node, i)
                if key > node.keys[i]:
                    i += 1
            self._insert_non_full(node.children[i], key, owner_id)

    def _range_search_recursive(self, node: BTreeNode, start: Any, end: Any, result: List[str]) -> None:
        i = 0
        while i < len(node.keys) and node.keys[i] < start:
            i += 1
            
        if node.leaf:
            while i < len(node.keys) and node.keys[i] <= end:
                result.extend(node.values[node.keys[i]])
                i += 1
        else:
            if i < len(node.keys):
                self._range_search_recursive(node.children[i], start, end, result)
            
            while i < len(node.keys) and node.keys[i] <= end:
                result.extend(node.values[node.keys[i]])
                i += 1
                if i < len(node.children):
                    self._range_search_recursive(node.children[i], start, end, result)

    def _serialize_tree(self, node: BTreeNode) -> Dict:
        """序列化 B-tree 节点"""
        return {
            'leaf': node.leaf,
            'keys': [k.isoformat() if isinstance(k, datetime) else k for k in node.keys],
            'values': node.values,
            'children': [self._serialize_tree(child) for child in node.children]
        }

    def _deserialize_tree(self, data: Dict) -> BTreeNode:
        """反序列化 B-tree 节点"""
        node = BTreeNode(leaf=data['leaf'])
        node.keys = [
            datetime.fromisoformat(k) if isinstance(k, str) and self._is_iso_format(k) else k 
            for k in data['keys']
        ]
        node.values = data['values']
        node.children = [self._deserialize_tree(child) for child in data['children']]
        return node

    def _is_iso_format(self, value: str) -> bool:
        """检查字符串是否为 ISO 格式"""
        try:
            datetime.fromisoformat(value)
            return True
        except ValueError:
            return False

    def _search_recursive(self, node: BTreeNode, value: Any) -> List[str]:
        """递归搜索值"""
        i = 0
        while i < len(node.keys) and value > node.keys[i]:
            i += 1
            
        if i < len(node.keys) and value == node.keys[i]:
            return node.values[node.keys[i]]
            
        if node.leaf:
            return []
            
        return self._search_recursive(node.children[i], value)

    def _remove_recursive(self, node: BTreeNode, owner_id: str) -> None:
        """递归删除 owner_id"""
        # 从当前节点的所有键值对中删除
        keys_to_remove = []
        for key in node.keys:
            if owner_id in node.values[key]:
                node.values[key].remove(owner_id)
                if not node.values[key]:
                    keys_to_remove.append(key)
        
        # 删除空值的键
        for key in keys_to_remove:
            idx = node.keys.index(key)
            node.keys.pop(idx)
            del node.values[key]
            
            # 如果是非叶子节点，需要重组子节点
            if not node.leaf and idx < len(node.children):
                child1 = node.children[idx]
                child2 = node.children[idx + 1]
                node.children[idx:idx + 2] = [self._merge_nodes(child1, child2)]
        
        # 递归处理子节点
        if not node.leaf:
            for child in node.children:
                self._remove_recursive(child, owner_id)

    def _merge_nodes(self, node1: BTreeNode, node2: BTreeNode) -> BTreeNode:
        """合并两个节点"""
        merged = BTreeNode(leaf=node1.leaf)
        merged.keys = node1.keys + node2.keys
        merged.values = {**node1.values, **node2.values}
        if not node1.leaf:
            merged.children = node1.children + node2.children
        return merged

    def query(self, op: str, value1: Any, value2: Any = None) -> List[str]:
        """统一的查询接口
        
        Args:
            op: 比较操作符
            value1: 比较值1
            value2: 比较值2（仅在区间查询时使用）
            
        Returns:
            符合条件的 owner_id 列表
        """
        result = []
        
        if op in COMPARE_OPS:
            # 单值比较
            self._one_sided_search(self._tree, op, value1, result)
        elif op in RANGE_OPS:
            # 区间比较
            if value2 is None:
                raise ValueError(f"区间操作符 {op} 需要两个值")
            self._range_search(self._tree, op, value1, value2, result)
            
        return result

    def _one_sided_search(self, node: BTreeNode, op: str, value: Any, result: List[str]) -> None:
        """单值查询"""
        compare = COMPARE_OPS[op]
        i = 0
        
        while i < len(node.keys):
            if compare(node.keys[i], value):
                result.extend(node.values[node.keys[i]])
            
            # 根据操作符决定是否继续搜索子树
            if not node.leaf:
                if op in (">=", ">"):
                    if node.keys[i] < value:
                        i += 1
                        continue
                    self._collect_all_values(node.children[i], result)
                elif op in ("<=", "<"):
                    if node.keys[i] > value:
                        break
                    self._collect_all_values(node.children[i], result)
                elif op in ("==", "!="):
                    self._one_sided_search(node.children[i], op, value, result)
            i += 1
            
        if not node.leaf and i < len(node.children):
            self._one_sided_search(node.children[i], op, value, result)

    def _range_search(self, node: BTreeNode, op: str, start: Any, end: Any, result: List[str]) -> None:
        """区间查询"""
        compare = RANGE_OPS[op]
        i = 0
        
        while i < len(node.keys):
            if compare(node.keys[i], start, end):
                result.extend(node.values[node.keys[i]])
            
            if not node.leaf:
                if node.keys[i] >= start:
                    self._range_search(node.children[i], op, start, end, result)
            i += 1
            
        if not node.leaf and i < len(node.children):
            self._range_search(node.children[i], op, start, end, result)

class BTreeIndexBackend(IndexBackend):
    """B树索引后端"""
    def __init__(self, data_dir: str = None, filename: str = None,
                 index_fields: List[str] = None,
                 logger: Optional[logging.Logger] = None):
        self._indexes: Dict[str, BTreeIndex] = {}
        self._index_fields = index_fields or []
        self._data_dir = Path(data_dir) if data_dir else None
        self._filename = filename
        self.logger = logger
        
        for field in self._index_fields:
            self._indexes[field] = BTreeIndex()
        
        if data_dir and filename:
            self._load_indexes()

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引"""
        for field in self._index_fields:
            value = getattr(data, field, None)
            if value is None:
                continue
            
            if field not in self._indexes:
                self._indexes[field] = BTreeIndex()
            
            self._indexes[field].add(value, owner_id)
        
        self._save_indexes()

    def query(self, field: str, op: str, value1: Any, value2: Any = None) -> List[str]:
        """统一的查询接口"""
        if field not in self._indexes:
            return []
            
        # 将字符串转换回 datetime 对象
        if isinstance(value1, str):
            try:
                value1 = datetime.fromisoformat(value1)
            except ValueError:
                pass
        
        if value2 and isinstance(value2, str):
            try:
                value2 = datetime.fromisoformat(value2)
            except ValueError:
                pass
        
        if op in COMPARE_OPS:
            return self._indexes[field].query(op, value1)
        elif op in RANGE_OPS:
            return self._indexes[field].query(op, value1, value2)
        return []

    def find_with_index(self, field: str, value: Any) -> List[str]:
        if field not in self._indexes:
            return []
        return self._indexes[field].search(value)

    def find_range(self, field: str, start: Any, end: Any) -> List[str]:
        if field not in self._indexes:
            return []
        return self._indexes[field].range_search(start, end)

    def has_index(self, field: str) -> bool:
        return field in self._index_fields

    def remove_from_index(self, owner_id: str) -> None:
        """删除索引"""
        for field, field_index in self._indexes.items():
            empty_keys = []  # 记录需要删除的键
            for value, owner_ids in field_index.items():
                if owner_id in owner_ids:
                    owner_ids.remove(owner_id)
                    if not owner_ids:
                        empty_keys.append(value)
            
            # 删除空值的键
            for key in empty_keys:
                field_index.pop(key, None)
        
        self._save_indexes()

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建所有B树索引"""
        self._indexes = {}
        
        data = data_iterator()
        for owner_id, item in data:
            self.update_index(item, owner_id)
        
        self._save_indexes()
        if self.logger:
            self.logger.info(f"B树索引重建完成，共处理 {len(data)} 条记录")

    def _get_index_path(self, field: str) -> Optional[Path]:
        if not (self._data_dir and self._filename):
            return None
        return self._data_dir / ".indexes" / f"{self._filename}.{field}.btree"

    def _load_indexes(self) -> None:
        for field in self._index_fields:
            path = self._get_index_path(field)
            if path and path.exists():
                try:
                    self._indexes[field].load(path)
                except Exception as e:
                    self.logger.error(f"加载B树索引失败 {field}: {e}")

    def _save_indexes(self) -> None:
        if not self._data_dir:
            return
            
        (self._data_dir / ".indexes").mkdir(parents=True, exist_ok=True)
        
        for field, index in self._indexes.items():
            path = self._get_index_path(field)
            if path:
                try:
                    index.save(path)
                except Exception as e:
                    self.logger.error(f"保存B树索引失败 {field}: {e}")

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
        self._hash_backend.update_index(data, owner_id)
        if self._btree_backend:
            self._btree_backend.update_index(data, owner_id)

    def remove_from_index(self, owner_id: str) -> None:
        self._hash_backend.remove_from_index(owner_id)
        if self._btree_backend:
            self._btree_backend.remove_from_index(owner_id)

    def find_with_index(self, field: str, value: Any) -> List[str]:
        if field not in self._index_config:
            return []
            
        index_type = self._index_config[field]
        if index_type == IndexType.HASH:
            return self._hash_backend.find_with_index(field, value)
        elif index_type == IndexType.BTREE and self._btree_backend:
            return self._btree_backend.find_with_index(field, value)
        return []

    def find_range(self, field: str, start: Any, end: Any) -> List[str]:
        if (field in self._index_config and
            self._index_config[field] == IndexType.BTREE and
            self._btree_backend):
            return self._btree_backend.find_range(field, start, end)
        return []

    def has_index(self, field: str) -> bool:
        return field in self._index_config

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        self._hash_backend.rebuild_indexes(data_iterator)
        if self._btree_backend:
            self._btree_backend.rebuild_indexes(data_iterator)

    def query(self, field: str, op: str, value1: Any, value2: Any = None) -> List[str]:
        """统一的查询接口"""
        if field not in self._index_config:
            return []
            
        index_type = self._index_config[field]
        if index_type == IndexType.HASH:
            if op not in ("==", "!="):
                self.logger.warning(f"哈希索引不支持 {op} 操作符")
                return []
            results = self._hash_backend.find_with_index(field, value1)
            return [] if op == "!=" else results
            
        elif index_type == IndexType.BTREE and self._btree_backend:
            return self._btree_backend.query(field, op, value1, value2)
            
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