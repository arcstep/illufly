from typing import Dict, Type, Any, Optional, List, Callable, Union
from pathlib import Path
import logging
from datetime import datetime
import json
from collections import defaultdict
from functools import lru_cache

from .typed_index_backend import TypedIndexBackend, ErrorHandling, TypeMismatchError
from .ops import COMPARE_OPS, RANGE_OPS

class BTreeNode:
    """B树节点"""
    __slots__ = ['leaf', 'keys', 'values', 'children']
    
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
        self._cache = {}
        self._owner_to_keys = defaultdict(set)
        self._null_values = set()  # 新增：专门存储 None 值的集合
        print(f"初始化 BTreeIndex，order={order}")  # 调试日志
    
    @lru_cache(maxsize=1024)
    def add(self, value: Any, owner_id: str) -> None:
        """添加值到索引"""
        # 先移除该 owner_id 的旧值
        self.remove(owner_id)
        
        # 特殊处理 None 值
        if value is None:
            self._null_values.add(owner_id)
            return
            
        if self._tree.is_full(self._order):
            new_root = BTreeNode(leaf=False)
            new_root.children.append(self._tree)
            self._split_child(new_root, 0)
            self._tree = new_root
            
        self._insert_non_full(self._tree, value, owner_id)
        self._owner_to_keys[owner_id].add(value)
        self._cache.clear()
        # print(f"添加后的树结构: {self._debug_print_tree()}")  # 调试日志
    
    def remove(self, owner_id: str) -> None:
        """移除指定 owner_id 的所有值"""
        # 检查并移除 None 值
        self._null_values.discard(owner_id)
        
        # 获取该 owner_id 对应的所有键
        keys_to_remove = self._owner_to_keys.get(owner_id, set())
        
        for key in keys_to_remove:
            if key in self._tree.values:
                self._tree.values[key].remove(owner_id)
                if not self._tree.values[key]:  # 如果没有其他 owner，删除该键
                    self._remove_key(self._tree, key)
                    
        self._owner_to_keys.pop(owner_id, None)
        self._cache.clear()
    
    @lru_cache(maxsize=1024) 
    def search(self, value: Any) -> List[str]:
        if value in self._cache:
            return self._cache[value]
        result = self._search_recursive(self._tree, value)
        self._cache[value] = result
        return result
    
    @lru_cache(maxsize=1024)
    def range_search(self, start: Any, end: Any) -> List[str]:
        cache_key = (start, end)
        if cache_key in self._cache:
            return self._cache[cache_key]
        result = []
        self._range_search_recursive(self._tree, start, end, result)
        self._cache[cache_key] = result
        return result

    def save(self, path: Path) -> None:
        data = self._serialize_tree(self._tree)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    
    def load(self, path: Path) -> None:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._tree = self._deserialize_tree(data)
                self._cache.clear()

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
        """插入值到非满节点"""
        i = len(node.keys) - 1
        
        if node.leaf:
            # 特殊处理比较
            while i >= 0 and self._safe_compare(key, node.keys[i]) < 0:
                i -= 1
            i += 1
            
            # 检查是否已存在相同的键
            if i > 0 and self._safe_compare(key, node.keys[i-1]) == 0:
                i -= 1
                if owner_id not in node.values[node.keys[i]]:
                    node.values[node.keys[i]].append(owner_id)
            else:
                node.keys.insert(i, key)
                node.values[key] = [owner_id]
        else:
            while i >= 0 and self._safe_compare(key, node.keys[i]) < 0:
                i -= 1
            i += 1
            
            if node.children[i].is_full(self._order):
                self._split_child(node, i)
                if self._safe_compare(key, node.keys[i]) > 0:
                    i += 1
            self._insert_non_full(node.children[i], key, owner_id)

    def _safe_compare(self, x: Any, y: Any) -> int:
        """改进的安全比较函数"""
        # 处理 None 值
        if x is None or y is None:
            if x is None and y is None:
                return 0
            return -1 if x is None else 1
            
        # 处理复合键
        if isinstance(x, tuple) and isinstance(y, tuple):
            for a, b in zip(x, y):
                result = self._safe_compare(a, b)
                if result != 0:
                    return result
            # 如果所有元素都相等，比较长度
            return len(x) - len(y)
            
        # 处理日期时间
        if isinstance(x, datetime) and isinstance(y, datetime):
            if x < y:
                return -1
            elif x > y:
                return 1
            return 0
            
        # 处理数值类型
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if x < y:
                return -1
            elif x > y:
                return 1
            return 0
            
        # 其他类型转换为字符串比较
        try:
            str_x = str(x)
            str_y = str(y)
            if str_x < str_y:
                return -1
            elif str_x > str_y:
                return 1
            return 0
        except Exception:
            # 如果比较失败，将它们视为相等
            return 0

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
            'keys': [
                {
                    'type': 'datetime',
                    'value': key.isoformat()
                } if isinstance(key, datetime) else key
                for key in node.keys
            ],
            'values': node.values,
            'children': [self._serialize_tree(child) for child in node.children]
        }

    def _deserialize_tree(self, data: Dict) -> BTreeNode:
        """反序列化 B-tree 节点"""
        node = BTreeNode(leaf=data['leaf'])
        node.keys = [
            datetime.fromisoformat(k['value']) if isinstance(k, dict) and k.get('type') == 'datetime'
            else k
            for k in data['keys']
        ]
        node.values = data['values']
        node.children = [self._deserialize_tree(child) for child in data['children']]
        return node

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
        """递归删除指定的 owner_id"""
        empty_keys = []
        for key in node.keys:
            if owner_id in node.values[key]:
                node.values[key].remove(owner_id)
                if not node.values[key]:
                    empty_keys.append(key)
        
        for key in empty_keys:
            idx = node.keys.index(key)
            node.keys.pop(idx)
            del node.values[key]
            
            if not node.leaf and idx < len(node.children):
                child1 = node.children[idx]
                child2 = node.children[idx + 1]
                node.children[idx:idx + 2] = [self._merge_nodes(child1, child2)]
        
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
        """改进的查询接口"""
        result = []
        
        try:
            if op == "==":
                if value1 is None:
                    return list(self._null_values)
                for key in self._tree.keys:
                    if self._safe_compare(key, value1) == 0:
                        result.extend(self._tree.values[key])
                        
            elif op == "!=":
                if value1 is None:
                    for key in self._tree.keys:
                        result.extend(self._tree.values[key])
                else:
                    result.extend(self._null_values)
                    for key in self._tree.keys:
                        if self._safe_compare(key, value1) != 0:
                            result.extend(self._tree.values[key])
                            
            elif op in (">", ">=", "<", "<="):
                self._one_sided_search(self._tree, op, value1, result)
                
            elif op in RANGE_OPS:
                if value2 is None:
                    raise ValueError(f"区间操作符 {op} 需要两个值")
                self._range_search(self._tree, op, value1, value2, result)
                
            else:
                raise ValueError(f"不支持的操作符: {op}")
                
        except Exception as e:
            return []
            
        return result

    def _one_sided_search(self, node: BTreeNode, op: str, value: Any, result: List[str]) -> None:
        """改进的单侧查询实现，移除调试输出"""
        i = 0
        while i < len(node.keys):
            current_key = node.keys[i]
            cmp_result = self._safe_compare(current_key, value)
            
            if op == ">":
                if cmp_result > 0:
                    result.extend(node.values[current_key])
            elif op == ">=":
                if cmp_result >= 0:
                    result.extend(node.values[current_key])
            elif op == "<":
                if cmp_result < 0:
                    result.extend(node.values[current_key])
            elif op == "<=":
                if cmp_result <= 0:
                    result.extend(node.values[current_key])
                    
            if not node.leaf:
                if op in (">", ">="):
                    if cmp_result >= 0 and i + 1 < len(node.children):
                        self._one_sided_search(node.children[i + 1], op, value, result)
                else:  # <, <=
                    if cmp_result <= 0:
                        if i < len(node.children):
                            self._one_sided_search(node.children[i], op, value, result)
                            
            i += 1
            
        if not node.leaf and i < len(node.children):
            if op in (">", ">="):
                self._one_sided_search(node.children[i], op, value, result)

    def _range_search(self, node: BTreeNode, op: str, start: Any, end: Any, result: List[str]) -> None:
        """改进的区间查询实现"""
        def in_range(key: Any) -> bool:
            """判断键是否在定范围内"""
            if isinstance(key, tuple) and isinstance(start, tuple) and isinstance(end, tuple):
                # 对于复合键，需要分别比较每个组件
                start_cmp = all(self._safe_compare(k, s) >= 0 for k, s in zip(key, start))
                end_cmp = all(self._safe_compare(k, e) <= 0 for k, e in zip(key, end))
                
                if op == "[]":
                    return start_cmp and end_cmp
                elif op == "()":
                    start_cmp = all(self._safe_compare(k, s) > 0 for k, s in zip(key, start))
                    end_cmp = all(self._safe_compare(k, e) < 0 for k, e in zip(key, end))
                    return start_cmp and end_cmp
                elif op == "[)":
                    end_cmp = all(self._safe_compare(k, e) < 0 for k, e in zip(key, end))
                    return start_cmp and end_cmp
                elif op == "(]":
                    start_cmp = all(self._safe_compare(k, s) > 0 for k, s in zip(key, start))
                    return start_cmp and end_cmp
            else:
                # 非复合键的处理保持不变
                start_cmp = self._safe_compare(key, start)
                end_cmp = self._safe_compare(key, end)
                
                if op == "[]":
                    return start_cmp >= 0 and end_cmp <= 0
                elif op == "()":
                    return start_cmp > 0 and end_cmp < 0
                elif op == "[)":
                    return start_cmp >= 0 and end_cmp < 0
                elif op == "(]":
                    return start_cmp > 0 and end_cmp <= 0
            return False

        i = 0
        
        # 找到第一个可能在范围内的位置
        while i < len(node.keys) and self._safe_compare(node.keys[i], start) < 0:
            i += 1

        # 如果是叶子节点，直接处理范围内的键
        if node.leaf:
            while i < len(node.keys) and self._safe_compare(node.keys[i], end) <= 0:
                if in_range(node.keys[i]):
                    result.extend(node.values[node.keys[i]])
                i += 1
            return

        # 非叶子节点的处理
        # 如果当前位置的子节点可能包含范围内的值，先处理子节点
        if i < len(node.children):
            self._range_search(node.children[i], op, start, end, result)

        # 处理当前节点中的键和右侧子节点
        while i < len(node.keys) and self._safe_compare(node.keys[i], end) <= 0:
            if in_range(node.keys[i]):
                result.extend(node.values[node.keys[i]])
            
            i += 1
            # 处理下一个子节点
            if i < len(node.children):
                self._range_search(node.children[i], op, start, end, result)

    def _serialize_value(self, value: Any) -> Union[str, int, float, bool, None, tuple]:
        """序列化值以便在B树中存储和比较
        
        扩展基类的序列化方法，增加对复合键和特殊类型的支持
        """
        if value is None:
            return None
        
        # 处理复合键
        if isinstance(value, (list, tuple)):
            return tuple(self._serialize_value(v) for v in value)
        
        # 处理日期时间
        if isinstance(value, datetime):
            return value.isoformat()
        
        # 处理基本类型
        if isinstance(value, (str, int, float, bool)):
            return value
        
        # 其他类型转换为字符串
        return str(value)

    def _deserialize_value(self, value: Any, field: str) -> Any:
        """反序列化B树中存储的值
        
        扩展基类的反序列化方法，增加对复合键和特殊类型的支持
        """
        if value is None:
            return None
        
        field_type = self._field_types.get(field)
        
        # 处理复合键
        if isinstance(value, (list, tuple)):
            return tuple(self._deserialize_value(v, field) for v in value)
        
        # 处理日期时间
        if field_type == datetime and isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                self.logger.warning(f"无法将值 {value} 转换为日期时间")
                return None
            
        # 处理基本类型
        try:
            if field_type in (int, float, str, bool):
                return field_type(value)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"类型转换失败: {e}")
            if self._error_handling == ErrorHandling.STRICT:
                raise TypeMismatchError(field, value, field_type)
            return None
        
        return value

    def _debug_print_tree(self) -> str:
        """用于调试的树结构打印方法"""
        def _print_node(node: BTreeNode, level: int = 0) -> List[str]:
            indent = "  " * level
            lines = [f"{indent}Keys: {node.keys}"]
            lines.append(f"{indent}Values: {node.values}")
            if not node.leaf:
                for i, child in enumerate(node.children):
                    lines.append(f"{indent}Child {i}:")
                    lines.extend(_print_node(child, level + 1))
            return lines
        
        return "\n".join(_print_node(self._tree))

    def _remove_key(self, node: BTreeNode, key: Any) -> None:
        """从节点中移除指定的键"""
        if key in node.keys:
            idx = node.keys.index(key)
            node.keys.pop(idx)
            del node.values[key]

class BTreeIndexBackend(TypedIndexBackend):
    """支持类型安全的B树索引后端"""
    
    def __init__(self,
                 data_dir: str = None,
                 filename: str = None,
                 index_fields: List[str] = None,
                 field_types: Dict[str, Type] = None,
                 error_handling: ErrorHandling = ErrorHandling.WARNING,
                 logger: Optional[logging.Logger] = None):
        # 初始化类型检查基类
        super().__init__(field_types, error_handling, logger)
        
        self._indexes: Dict[str, BTreeIndex] = {}
        self._index_fields = index_fields or []
        self._data_dir = Path(data_dir) if data_dir else None
        self._filename = filename
        
        # 初始化索引
        for field in self._index_fields:
            if field not in self._field_types:
                self._field_types[field] = str
            self._indexes[field] = BTreeIndex()
            
        if data_dir and filename:
            self._load_indexes()

    def _serialize_value(self, value: Any) -> Union[str, int, float, bool, None, tuple]:
        """序列化值以便在B树中存储和比较
        
        扩展基类的序列化方法，增加对复合键和特殊类型的支持
        """
        if value is None:
            return None
        
        # 处理复合键
        if isinstance(value, (list, tuple)):
            return tuple(self._serialize_value(v) for v in value)
        
        # 处理日期时间
        if isinstance(value, datetime):
            return value.isoformat()
        
        # 处理基本类型
        if isinstance(value, (str, int, float, bool)):
            return value
        
        # 其他类型转换为字符串
        return str(value)

    def _deserialize_value(self, value: Any, field: str) -> Any:
        """反序列化B树中存储的值
        
        扩展基类的反序列化方法，增加对复合键和特殊类型的支持
        """
        if value is None:
            return None
        
        field_type = self._field_types.get(field)
        
        # 处理复合键
        if isinstance(value, (list, tuple)):
            return tuple(self._deserialize_value(v, field) for v in value)
        
        # 处理日期时间
        if field_type == datetime and isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                self.logger.warning(f"无法将值 {value} 转换为日期时间")
                return None
            
        # 处理基本类型
        try:
            if field_type in (int, float, str, bool):
                return field_type(value)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"类型转换失败: {e}")
            if self._error_handling == ErrorHandling.STRICT:
                raise TypeMismatchError(field, value, field_type)
            return None
        
        return value

    def update_index(self, data: Dict[str, Any], owner_id: str) -> None:
        """更新索引，包含类型检查和序列化"""
        self.remove_from_index(owner_id)
        
        for field in self._index_fields:
            value = self._get_value_by_path(data, field)
            if value is None:
                continue
                
            try:
                # 先进行类型检查和转换
                if not self._validate_value(field, value):
                    continue
                    
                converted_value = self._convert_value(field, value)
                if converted_value is not None:
                    # 序列化转换后的值，使用B树特定的序列化方法
                    serialized_value = self._serialize_value(converted_value)
                    self._indexes[field].add(serialized_value, owner_id)
                    
            except TypeMismatchError as e:
                if self._error_handling == ErrorHandling.STRICT:
                    raise
                self.logger.warning(str(e))
                continue
                
        self._save_indexes()

    def query(self, field: str, op: str, value1: Any, value2: Any = None) -> List[str]:
        """带类型检查的查询接口"""
        if field not in self._indexes:
            return []
            
        btree = self._indexes[field]
        
        try:
            # 类型检查和转换
            value1 = self._convert_value(field, value1)
            if value1 is None and op != "==":  # 允许 None 值的等值查询
                return []
                
            if value2 is not None:
                value2 = self._convert_value(field, value2)
                if value2 is None:
                    return []
            
            # 序列化转换后的值
            value1 = self._serialize_value(value1)
            if value2 is not None:
                value2 = self._serialize_value(value2)
            
            if op in COMPARE_OPS:
                if op == "==":
                    return btree.search(value1)
                else:
                    if op in (">", ">="):
                        return btree.range_search(value1, float('inf'))
                    else:  # <, <=
                        return btree.range_search(float('-inf'), value1)
            elif op in RANGE_OPS:
                if value2 is None:
                    raise ValueError(f"区间操作符 {op} 需要两个值")
                return btree.range_search(value1, value2)
                
        except (TypeMismatchError, ValueError) as e:
            if self._error_handling == ErrorHandling.STRICT:
                raise
            self.logger.warning(f"查询执行失败: {e}")
            return []
            
        return []

    def find_with_index(self, field: str, value: Any) -> List[str]:
        """带类型检查的等值查询"""
        if field not in self._indexes:
            return []
            
        try:
            converted_value = self._convert_value(field, value)
            if converted_value is None:
                return []
            serialized_value = self._serialize_value(converted_value)
            return self._indexes[field].search(serialized_value)
        except TypeMismatchError as e:
            if self._error_handling == ErrorHandling.STRICT:
                raise
            self.logger.warning(str(e))
            return []

    def find_range(self, field: str, start: Any, end: Any) -> List[str]:
        """带类型检查的范围查询"""
        if field not in self._indexes:
            return []
            
        try:
            start_value = self._convert_value(field, start)
            end_value = self._convert_value(field, end)
            
            if start_value is None or end_value is None:
                return []
                
            serialized_start = self._serialize_value(start_value)
            serialized_end = self._serialize_value(end_value)
            
            return self._indexes[field].range_search(serialized_start, serialized_end)
        except TypeMismatchError as e:
            if self._error_handling == ErrorHandling.STRICT:
                raise
            self.logger.warning(str(e))
            return []

    def has_index(self, field: str) -> bool:
        return field in self._index_fields

    def remove_from_index(self, owner_id: str) -> None:
        """删除索引"""
        for field, btree_index in self._indexes.items():
            btree_index.remove(owner_id)
        
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
        return self._data_dir / ".indexes" / f"{self._filename}.{field}"

    def _load_indexes(self) -> None:
        """加载索引和类型信息"""
        for field in self._index_fields:
            path = self._get_index_path(field)
            if path and (path.with_suffix('.btree')).exists():
                try:
                    with open(f"{path}.btree", 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        type_name = data['type']
                        if type_name == 'datetime':
                            self._field_types[field] = datetime
                        elif type_name == 'int':
                            self._field_types[field] = int
                        elif type_name == 'float':
                            self._field_types[field] = float
                        elif type_name == 'str':
                            self._field_types[field] = str
                        elif type_name == 'bool':
                            self._field_types[field] = bool
                            
                        self._indexes[field] = BTreeIndex()
                        self._indexes[field]._tree = self._indexes[field]._deserialize_tree(data['index'])
                except Exception as e:
                    self.logger.error(f"加载B树索引失败 {field}: {e}")

    def _save_indexes(self) -> None:
        """保存索引和类型信息"""
        if not self._data_dir:
            return
            
        (self._data_dir / ".indexes").mkdir(parents=True, exist_ok=True)
        
        for field, index in self._indexes.items():
            path = self._get_index_path(field)
            if not path:
                continue
                
            try:
                # 确保字段类型存在
                field_type = self._field_types.get(field, str)
                data = {
                    'type': field_type.__name__,
                    'index': index._serialize_tree(index._tree)
                }
                with open(f"{path}.btree", 'w', encoding='utf-8') as f:
                    json.dump(data, f)
            except Exception as e:
                # 使用 print 作为后备方案
                if self.logger:
                    self.logger.error(f"保存B树索引失败 {field}: {e}")
                else:
                    print(f"保存B树索引失败 {field}: {e}")