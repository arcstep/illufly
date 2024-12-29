from typing import Dict, Any, List, Callable, Optional, Union
from pathlib import Path
import json
from datetime import datetime

from .index_backend import IndexBackend
from .config import IndexConfig

class BTreeNode:
    """B树节点
    
    Attributes:
        leaf (bool): 是否是叶子节点
        keys (List[str]): 键列表（已排序）
        values (Dict[str, List[str]]): 键到owner_id列表的映射
        children (List[BTreeNode]): 子节点列表
    """
    __slots__ = ['leaf', 'keys', 'values', 'children']
    
    def __init__(self, leaf: bool = False):
        self.leaf = leaf
        self.keys: List[str] = []
        self.values: Dict[str, List[str]] = {}
        self.children: List['BTreeNode'] = []

    def is_full(self, order: int) -> bool:
        """检查节点是否已满"""
        return len(self.keys) >= 2 * order - 1

class BTreeIndexBackend(IndexBackend):
    """基于B树的索引实现
    
    特点：
    - 支持范围查询
    - 数据自动排序
    - 适用于大型数据集
    - 磁盘持久化支持
    
    Attributes:
        _order (int): B树的阶
        _trees (Dict[str, BTreeNode]): 字段到B树根节点的映射
        _null_values (Dict[str, set]): 存储每个字段的空值owner_id
    """
    
    def __init__(self, 
                 field_types: Dict[str, Any] = None,
                 config: Optional[IndexConfig] = None,
                 data_dir: str = None,
                 filename: str = None,
                 order: int = 4):
        """初始化B树索引后端
        
        Args:
            field_types: 字段类型约束
            config: 索引配置
            data_dir: 索引文件存储目录（可选）
            filename: 索引文件名（可选）
            order: B树的阶，默认为4
        """
        super().__init__(field_types=field_types, config=config)
        self._order = order
        self._trees = {}
        self._null_values = defaultdict(set)
        self._data_dir = Path(data_dir) if data_dir else None
        self._filename = filename
        
        # 为每个字段创建B树
        for field in self._field_types:
            self._trees[field] = BTreeNode(leaf=True)
        
        if self._data_dir and filename:
            self._load_indexes()

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引
        
        根据配置的更新策略处理索引更新
        """
        try:
            # 移除旧索引
            self.remove_from_index(owner_id)
            
            # 根据更新策略处理
            if self._config.update_strategy == "async":
                # TODO: 实现异步更新逻辑
                pass
            elif self._config.update_strategy == "batch":
                # TODO: 实现批量更新逻辑
                pass
            else:  # 同步更新
                for field in self._field_types:
                    value = self._get_value_by_path(data, field)
                    if value is None:
                        self._null_values[field].add(owner_id)
                        continue
                        
                    index_key = self.convert_to_index_key(value, field)
                    self._insert(field, index_key, owner_id)
            
            self._stats["updates"] += 1
            
            # 如果启用了持久化，保存索引
            if self._config.persist_path:
                self._save_indexes()
                
        except Exception as e:
            self.logger.error(f"更新索引失败: {e}")
            raise

    def _insert_to_btree(self, field: str, key: str, owner_id: str) -> None:
        """向B树插入键值对
        
        Args:
            field: 字段名
            key: 索引键
            owner_id: 数据所有者ID
        """
        tree = self._trees[field]
        
        # 如果根节点已满，需要分裂
        if tree.is_full(self._order):
            new_root = BTreeNode(leaf=False)
            new_root.children.append(tree)
            self._split_child(new_root, 0)
            self._trees[field] = new_root
            tree = new_root
        
        self._insert_non_full(tree, key, owner_id)

    def _split_child(self, parent: BTreeNode, index: int) -> None:
        """分裂子节点
        
        Args:
            parent: 父节点
            index: 要分裂的子节点索引
        """
        child = parent.children[index]
        new_node = BTreeNode(leaf=child.leaf)
        
        # 分裂点
        mid = self._order - 1
        mid_key = child.keys[mid]
        
        # 移动键和值
        parent.keys.insert(index, mid_key)
        parent.values[mid_key] = child.values[mid_key]
        
        new_node.keys = child.keys[mid + 1:]
        child.keys = child.keys[:mid]
        
        # 移动值
        for key in new_node.keys:
            new_node.values[key] = child.values[key]
            del child.values[key]
        
        # 如果不是叶子节点，移动子节点
        if not child.leaf:
            new_node.children = child.children[mid + 1:]
            child.children = child.children[:mid + 1]
        
        parent.children.insert(index + 1, new_node)

    def _insert_non_full(self, node: BTreeNode, key: str, owner_id: str) -> None:
        """向非满节点插入键值对
        
        Args:
            node: 目标节点
            key: 索引键
            owner_id: 数据所有者ID
        """
        i = len(node.keys) - 1
        
        if node.leaf:
            # 找到插入位置
            while i >= 0 and key < node.keys[i]:
                i -= 1
            i += 1
            
            # 插入键和值
            node.keys.insert(i, key)
            node.values[key] = [owner_id]
        else:
            # 找到合适的子节点
            while i >= 0 and key < node.keys[i]:
                i -= 1
            i += 1
            
            # 如果子节点已满，先分裂
            if node.children[i].is_full(self._order):
                self._split_child(node, i)
                if key > node.keys[i]:
                    i += 1
            
            self._insert_non_full(node.children[i], key, owner_id)

    def find_with_index(self, field: str, value: Any) -> List[str]:
        """使用索引查找数据
        
        Args:
            field: 索引字段
            value: 查找值
            
        Returns:
            List[str]: 匹配的所有者ID列表
        """
        if not self.has_index(field):
            return []
            
        try:
            # 处理空值
            if value is None:
                return list(self._null_values[field])
            
            index_key = self.convert_to_index_key(value, field)
            result = self._search_btree(self._trees[field], index_key)
            self._update_stats("queries")
            return result
        except Exception as e:
            self.logger.warning(f"索引查询失败: {e}")
            return []

    def _search_btree(self, node: BTreeNode, key: str) -> List[str]:
        """在B树中搜索键
        
        Args:
            node: 当前节点
            key: 要搜索的键
            
        Returns:
            List[str]: 匹配的owner_id列表
        """
        i = 0
        while i < len(node.keys) and key > node.keys[i]:
            i += 1
            
        if i < len(node.keys) and key == node.keys[i]:
            return node.values[node.keys[i]]
            
        if node.leaf:
            return []
            
        return self._search_btree(node.children[i], key)

    def remove_from_index(self, owner_id: str) -> None:
        """删除指定所有者的所有索引
        
        Args:
            owner_id: 数据所有者ID
        """
        # 从空值集合中移除
        for null_set in self._null_values.values():
            null_set.discard(owner_id)
        
        # 从B树中移除
        for field, tree in self._trees.items():
            self._remove_from_btree(tree, owner_id)
        
        self._save_indexes()

    def _remove_from_btree(self, node: BTreeNode, owner_id: str) -> None:
        """从B树节点中移除owner_id
        
        Args:
            node: 当前节点
            owner_id: 要移除的owner_id
        """
        empty_keys = []
        for key in node.keys:
            if owner_id in node.values[key]:
                node.values[key].remove(owner_id)
                if not node.values[key]:
                    empty_keys.append(key)
        
        # 移除空键
        for key in empty_keys:
            idx = node.keys.index(key)
            node.keys.pop(idx)
            del node.values[key]
        
        # 递归处理子节点
        if not node.leaf:
            for child in node.children:
                self._remove_from_btree(child, owner_id)

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建所有索引
        
        Args:
            data_iterator: 返回(owner_id, data)元组列表的迭代器
        """
        # 重置所有B树
        self._trees = {field: BTreeNode(leaf=True) for field in self._field_types}
        self._null_values = defaultdict(set)
        
        # 重建索引
        for owner_id, item in data_iterator():
            self.update_index(item, owner_id)
        
        self._save_indexes()
        self._stats["last_rebuild"] = True

    def get_index_size(self) -> int:
        """获取索引大小（键的总数）"""
        return sum(len(tree.keys) for tree in self._trees.values())

    def get_index_memory_usage(self) -> int:
        """估算索引内存使用量（字节）"""
        total_bytes = 0
        for field, tree in self._trees.items():
            # 递归计算每个节点的内存使用
            def calc_node_size(node: BTreeNode) -> int:
                size = 0
                size += sum(len(k.encode()) for k in node.keys)  # 键
                size += sum(sum(len(v.encode()) for v in values) 
                          for values in node.values.values())  # 值
                if not node.leaf:
                    size += sum(calc_node_size(child) for child in node.children)
                return size
            
            total_bytes += calc_node_size(tree)
            total_bytes += sum(len(v.encode()) for v in self._null_values[field])
        
        return total_bytes

    def _save_indexes(self) -> None:
        """保存索引到文件"""
        if not (self._data_dir and self._filename):
            return

        index_path = self._get_index_path()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            data = {
                'config': self._config.model_dump(),  # 保存配置
                'order': self._order,
                'trees': {field: self._serialize_tree(tree) 
                         for field, tree in self._trees.items()},
                'null_values': {field: list(values) 
                              for field, values in self._null_values.items()}
            }
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存索引失败: {e}")

    def _serialize_tree(self, node: BTreeNode) -> Dict:
        """序列化B树节点
        
        Args:
            node: 要序列化的节点
            
        Returns:
            Dict: 序列化后的节点数据
        """
        return {
            'leaf': node.leaf,
            'keys': node.keys,
            'values': node.values,
            'children': [self._serialize_tree(child) for child in node.children]
        }

    def _load_indexes(self) -> None:
        """从文件加载索引"""
        index_path = self._get_index_path()
        if not index_path.exists():
            return

        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 加载配置
                if 'config' in data:
                    self._config = IndexConfig.model_validate(data['config'])
                self._order = data.get('order', 4)
                self._trees = {
                    field: self._deserialize_tree(tree_data)
                    for field, tree_data in data.get('trees', {}).items()
                }
                self._null_values = defaultdict(set, {
                    field: set(values)
                    for field, values in data.get('null_values', {}).items()
                })
        except Exception as e:
            self.logger.error(f"加载索引失败: {e}")
            self._trees = {field: BTreeNode(leaf=True) for field in self._field_types}
            self._null_values = defaultdict(set)

    def _deserialize_tree(self, data: Dict) -> BTreeNode:
        """反序列化B树节点
        
        Args:
            data: 序列化的节点数据
            
        Returns:
            BTreeNode: 重建的节点
        """
        node = BTreeNode(leaf=data['leaf'])
        node.keys = data['keys']
        node.values = data['values']
        node.children = [self._deserialize_tree(child) for child in data['children']]
        return node

    def _get_index_path(self) -> Optional[Path]:
        """获取索引文件路径"""
        if not (self._data_dir and self._filename):
            return None
        return self._data_dir / ".indexes" / f"{self._filename}.btree"

    def has_index(self, field: str) -> bool:
        """检查字段是否已建立索引"""
        return field in self._trees