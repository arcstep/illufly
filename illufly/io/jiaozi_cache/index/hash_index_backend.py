from typing import Dict, Any, List, Callable, Optional
from collections import defaultdict
import json
from pathlib import Path

from .index_backend import IndexBackend
from .config import IndexConfig

class HashIndexBackend(IndexBackend):
    """基于哈希表的索引实现
    
    特点：
    - 使用内存哈希表存储索引
    - 支持可选的文件持久化
    - 支持精确匹配查询
    - 适用于小型到中型数据集
    
    存储结构：
    _indexes: Dict[str, Dict[str, List[str]]]
    - 第一层key: 字段名
    - 第二层key: 索引键（由convert_to_index_key生成）
    - value: owner_id列表
    """
    
    def __init__(self, 
                 field_types: Dict[str, Any] = None,
                 config: Optional[IndexConfig] = None,
                 data_dir: str = None,
                 filename: str = None):
        """初始化哈希索引后端
        
        Args:
            field_types: 字段类型约束
            config: 索引配置
            data_dir: 索引文件存储目录（可选）
            filename: 索引文件名（可选）
        """
        super().__init__(field_types=field_types, config=config)
        self._indexes = defaultdict(lambda: defaultdict(list))
        self._data_dir = Path(data_dir) if data_dir else None
        self._filename = filename
        
        if data_dir and filename:
            self._load_indexes()

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引
        
        Args:
            data: 要索引的数据对象
            owner_id: 数据所有者ID
        """
        try:
            # 移除旧索引
            self.remove_from_index(owner_id)
            
            # 为每个字段创建索引
            for field in self._field_types:
                value = self._get_value_by_path(data, field)
                if value is None:
                    continue
                
                # 处理列表类型的值
                if isinstance(value, (list, tuple, set)):
                    for item in value:
                        if self.is_field_type_valid(field, item):
                            index_key = self.convert_to_index_key(item, field)
                            self._add_to_index(field, index_key, owner_id)
                else:
                    if self.is_field_type_valid(field, value):
                        index_key = self.convert_to_index_key(value, field)
                        self._add_to_index(field, index_key, owner_id)
            
            self._update_stats("updates")
            self._save_indexes()
            
        except Exception as e:
            self.remove_from_index(owner_id)
            self._save_indexes()
            raise RuntimeError(f"索引更新失败: {e}")

    def _add_to_index(self, field: str, index_key: str, owner_id: str) -> None:
        """添加索引项
        
        Args:
            field: 字段名
            index_key: 索引键
            owner_id: 数据所有者ID
        """
        if owner_id not in self._indexes[field][index_key]:
            self._indexes[field][index_key].append(owner_id)

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
            index_key = self.convert_to_index_key(value, field)
            result = self._indexes[field][index_key]
            self._update_stats("queries")
            return result
        except Exception as e:
            self.logger.warning(f"索引查询失败: {e}")
            return []

    def has_index(self, field: str) -> bool:
        """检查字段是否已建立索引
        
        Args:
            field: 字段名
            
        Returns:
            bool: 是否存在索引
        """
        return field in self._indexes

    def remove_from_index(self, owner_id: str) -> None:
        """删除指定所有者的所有索引
        
        Args:
            owner_id: 数据所有者ID
        """
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

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建所有索引
        
        Args:
            data_iterator: 返回(owner_id, data)元组列表的迭代器
        """
        self._indexes.clear()
        
        for owner_id, item in data_iterator():
            self.update_index(item, owner_id)
        
        self._save_indexes()
        self._stats["last_rebuild"] = True

    def get_index_size(self) -> int:
        """获取索引大小（索引项数量）"""
        return sum(len(field_index) for field_index in self._indexes.values())

    def get_index_memory_usage(self) -> int:
        """估算索引内存使用量（字节）"""
        # 简单估算，实际使用可能需要更精确的计算
        total_bytes = 0
        for field, field_index in self._indexes.items():
            total_bytes += len(field.encode())  # 字段名
            for key, values in field_index.items():
                total_bytes += len(key.encode())  # 索引键
                total_bytes += sum(len(v.encode()) for v in values)  # owner_ids
        return total_bytes

    def _save_indexes(self) -> None:
        """保存索引到文件"""
        if not (self._data_dir and self._filename):
            return

        index_path = self._get_index_path()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            data = {
                'types': {field: str(t) for field, t in self._field_types.items()},
                'indexes': dict(self._indexes)
            }
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存索引失败: {e}")

    def _load_indexes(self) -> None:
        """从文件加载索引"""
        index_path = self._get_index_path()
        if not index_path.exists():
            return

        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._indexes = defaultdict(lambda: defaultdict(list))
                for field, field_index in data.get('indexes', {}).items():
                    for value, owner_ids in field_index.items():
                        self._indexes[field][value] = owner_ids
        except Exception as e:
            self.logger.error(f"加载索引失败: {e}")
            self._indexes = defaultdict(lambda: defaultdict(list))

    def _get_index_path(self) -> Optional[Path]:
        """获取索引文件路径"""
        if not (self._data_dir and self._filename):
            return None
        return self._data_dir / ".indexes" / self._filename

