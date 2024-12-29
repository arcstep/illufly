from typing import Dict, Any, List, Callable, Optional
from collections import defaultdict
import json
import logging
from pathlib import Path

from ....config import get_env
from .index_backend import IndexBackend
from .index_config import IndexConfig

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
    
    def __init__(
        self, 
        field_types: Dict[str, Any] = None,
        config: Optional[IndexConfig] = None,
        data_dir: str = None,
        segment: str = None,
        logger: Optional[logging.Logger] = None
    ):
        """初始化哈希索引后端
        
        Args:
            field_types: 字段类型约束
            config: 索引配置
            data_dir: 索引文件存储目录（可选）
            segment: 索引文件名（可选）
        """
        super().__init__(field_types=field_types, config=config)
        self._indexes = defaultdict(lambda: defaultdict(list))
        self._data_dir = Path(data_dir) if data_dir else get_env("ILLUFLY_JIAOZI_CACHE_DIR")
        self._segment = segment or "index.json"
        
        self.logger = logger or logging.getLogger(__name__)
        self.logger.info("初始化哈希索引后端: data_dir=%s, segment=%s", data_dir, segment)
        
        if data_dir and segment:
            self._load_indexes()

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引
        
        Args:
            data: 要索引的数据对象
            owner_id: 数据所有者ID
        """
        self.logger.debug("开始更新索引: owner_id=%s", owner_id)
        try:
            # 移除旧索引
            self.remove_from_index(owner_id)
            
            # 为每个字段创建索引
            for field in self._field_types:
                value = self._get_value_by_path(data, field)
                if value is None:
                    self.logger.debug("字段值为空，跳过索引: field=%s", field)
                    continue
                
                # 处理列表类型的值
                if isinstance(value, (list, tuple, set)):
                    self.logger.debug("处理列表类型字段: field=%s, length=%d", field, len(value))
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
            self.logger.info("索引更新成功: owner_id=%s", owner_id)
            
        except Exception as e:
            self.logger.error("索引更新失败: owner_id=%s, error=%s", owner_id, e)
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
        self.logger.debug("添加索引项: field=%s, index_key=%s, owner_id=%s", field, index_key, owner_id)
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
        self.logger.debug("开始索引查找: field=%s, value=%s", field, value)
        if not self.has_index(field):
            self.logger.warning("字段未建立索引: field=%s", field)
            return []
        
        try:
            index_key = self.convert_to_index_key(value, field)
            result = self._indexes[field][index_key]
            self._update_stats("queries")
            self.logger.debug("索引查找完成: field=%s, value=%s, matches=%d", field, value, len(result))
            return result
        except Exception as e:
            self.logger.warning("索引查询失败: field=%s, value=%s, error=%s", field, value, e)
            return []

    def has_index(self, field: str) -> bool:
        """检查字段是否已建立索引
        
        Args:
            field: 字段名
            
        Returns:
            bool: 是否存在索引
        """
        exists = field in self._indexes
        self.logger.debug("检查索引是否存在: field=%s, exists=%s", field, exists)
        return exists

    def remove_from_index(self, owner_id: str) -> None:
        """删除指定所有者的所有索引
        
        Args:
            owner_id: 数据所有者ID
        """
        self.logger.debug("开始删除索引: owner_id=%s", owner_id)
        removed_count = 0
        for field_index in self._indexes.values():
            empty_keys = []
            for value_key, owner_ids in field_index.items():
                if owner_id in owner_ids:
                    owner_ids.remove(owner_id)
                    removed_count += 1
                    if not owner_ids:
                        empty_keys.append(value_key)
            
            for key in empty_keys:
                field_index.pop(key)
        
        self.logger.info("索引删除完成: owner_id=%s, removed_items=%d", owner_id, removed_count)
        self._save_indexes()

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建所有索引
        
        Args:
            data_iterator: 返回(owner_id, data)元组列表的迭代器
        """
        self.logger.info("开始重建索引")
        self._indexes.clear()
        
        count = 0
        for owner_id, item in data_iterator():
            self.update_index(item, owner_id)
            count += 1
            if count % 1000 == 0:  # 每处理1000条打印一次进度
                self.logger.info("索引重建进度: processed=%d", count)
        
        self._save_indexes()
        self._stats["last_rebuild"] = True
        self.logger.info("索引重建完成: total_items=%d", count)

    def get_index_size(self) -> int:
        """获取索引大小（索引项数量）"""
        size = sum(len(field_index) for field_index in self._indexes.values())
        self.logger.debug("获取索引大小: size=%d", size)
        return size

    def get_index_memory_usage(self) -> int:
        """估算索引内存使用量（字节）"""
        # 简单估算，实际使用可能需要更精确的计算
        total_bytes = 0
        for field, field_index in self._indexes.items():
            total_bytes += len(field.encode())  # 字段名
            for key, values in field_index.items():
                total_bytes += len(key.encode())  # 索引键
                total_bytes += sum(len(v.encode()) for v in values)  # owner_ids
        
        self.logger.debug("获取索引内存使用量: bytes=%d", total_bytes)
        return total_bytes

    def _save_indexes(self) -> None:
        """保存索引到文件"""
        if not (self._data_dir and self._segment):
            self.logger.debug("未配置存储路径，跳过索引保存")
            return

        index_path = self._get_index_path()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self.logger.debug("开始保存索引: path=%s", index_path)
            data = {
                'types': {field: str(t) for field, t in self._field_types.items()},
                'indexes': dict(self._indexes)
            }
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info("索引保存成功: path=%s", index_path)
        except Exception as e:
            self.logger.error("保存索引失败: path=%s, error=%s", index_path, e)

    def _load_indexes(self) -> None:
        """从文件加载索引"""
        index_path = self._get_index_path()
        if not index_path.exists():
            self.logger.warning("索引文件不存在: path=%s", index_path)
            return

        try:
            self.logger.debug("开始加载索引: path=%s", index_path)
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._indexes = defaultdict(lambda: defaultdict(list))
                for field, field_index in data.get('indexes', {}).items():
                    for value, owner_ids in field_index.items():
                        self._indexes[field][value] = owner_ids
            self.logger.info("索引加载成功: path=%s", index_path)
        except Exception as e:
            self.logger.error("加载索引失败: path=%s, error=%s", index_path, e)
            self._indexes = defaultdict(lambda: defaultdict(list))

    def _get_index_path(self) -> Optional[Path]:
        """获取索引文件路径"""
        if not (self._data_dir and self._segment):
            return None
        return self._data_dir / ".indexes" / self._segment


