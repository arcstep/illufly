from typing import Dict, Any, List, Callable, Optional, Tuple, Union
from collections import defaultdict
import json
import logging
from pathlib import Path

from ....config import get_env
from .index_backend import IndexBackend
from .index_config import IndexConfig
from ..store import CachedJSONStorage

class HashIndexBackend(IndexBackend):
    """基于哈希表的索引实现"""
    
    def __init__(
        self, 
        field_types: Dict[str, Any] = None,
        config: Optional[IndexConfig] = None,
        data_dir: str = None,
        segment: str = None,
        logger: Optional[logging.Logger] = None,
        flush_interval: Optional[int] = None,
        flush_threshold: Optional[int] = None
    ):
        """初始化哈希索引后端"""
        super().__init__(field_types=field_types, config=config)
        self._indexes = defaultdict(lambda: defaultdict(list))
        
        # 使用带缓冲的存储后端
        self._writer = CachedJSONStorage(
            data_dir=data_dir,
            segment=segment or "index.json",
            flush_interval=flush_interval,
            flush_threshold=flush_threshold,
            logger=logger
        )
        
        self.logger = logger or logging.getLogger(__name__)
        
        # 加载索引
        self._load_indexes()

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引，使用基类的字段提取和转换逻辑"""
        self.logger.debug("开始更新索引: owner_id=%s", owner_id)
        try:
            # 移除旧索引
            self.remove_from_index(owner_id)
            
            # 为每个字段创建索引
            for field_path in self._field_types:
                # 使用基类的方法提取和转换值
                value, path_parts = self.extract_and_convert_value(data, field_path)
                if value is None:
                    self.logger.debug("字段值提取失败，跳过索引: field=%s, path=%s", 
                                    field_path, path_parts)
                    continue
                
                # 处理标签列表
                if isinstance(value, list):
                    self.logger.debug("处理列表字段: field=%s, values=%s", field_path, value)
                    for item in value:
                        index_key = str(item)  # 确保索引键是字符串
                        self._add_to_index(field_path, index_key, owner_id)
                else:
                    # 处理单个值
                    index_key = str(value)
                    self._add_to_index(field_path, index_key, owner_id)
            
            self._update_stats("updates")
            self._save_indexes()
            self.logger.info("索引更新成功: owner_id=%s", owner_id)
            
        except Exception as e:
            self.logger.error("索引更新失败: owner_id=%s, error=%s", owner_id, e)
            self.remove_from_index(owner_id)
            self._save_indexes()
            raise RuntimeError(f"索引更新失败: {e}")

    def _add_to_index(self, field: str, index_key: str, owner_id: str) -> None:
        """添加索引项"""
        self.logger.debug("添加索引项: field=%s, index_key=%s, owner_id=%s", field, index_key, owner_id)
        if owner_id not in self._indexes[field][index_key]:
            self._indexes[field][index_key].append(owner_id)

    def find_with_index(self, field: str, query_value: Any) -> List[str]:
        """使用索引进行精确匹配查询"""
        self.logger.debug("开始索引查找: field=%s, value=%s", field, query_value)
        
        try:
            # 使用基类的方法准备查询值
            value, error = self.prepare_query_value(field, query_value)
            if error:
                self.logger.warning("查询值无效: %s", error)
                return []
                
            if not self.has_index(field):
                self.logger.warning("字段未建立索引: field=%s", field)
                return []
            
            # 处理标签列表查询
            if isinstance(value, list):
                # 对于标签列表，我们返回包含任一标签的结果
                results = set()
                for item in value:
                    index_key = str(item)
                    results.update(self._indexes[field][index_key])
                result_list = list(results)
            else:
                # 单值精确匹配
                index_key = str(value)
                result_list = self._indexes[field][index_key].copy()
            
            self._update_stats("queries")
            self.logger.debug("索引查找完成: field=%s, value=%s, matches=%d", 
                            field, value, len(result_list))
            return result_list
            
        except Exception as e:
            self.logger.warning("索引查询失败: field=%s, value=%s, error=%s", 
                              field, query_value, e)
            return []

    def has_index(self, field: str) -> bool:
        """检查字段是否已建立索引"""
        if field not in self._field_types:
            self.logger.error("字段未定义索引类型: %s", field)
            return False

        exists = field in self._indexes
        self.logger.debug("检查索引是否存在: field=%s, exists=%s", field, exists)
        return exists

    def remove_from_index(self, owner_id: str) -> None:
        """删除指定所有者的所有索引"""
        self.logger.debug("开始删除索引: owner_id=%s", owner_id)
        removed_count = 0
        
        try:
            for field_index in self._indexes.values():
                empty_keys = []
                for value_key, owner_ids in field_index.items():
                    if owner_id in owner_ids:
                        owner_ids.remove(owner_id)
                        removed_count += 1
                        if not owner_ids:
                            empty_keys.append(value_key)
                
                # 清理空的索引项
                for key in empty_keys:
                    field_index.pop(key)
            
            self.logger.info("索引删除完成: owner_id=%s, removed_items=%d", 
                           owner_id, removed_count)
            self._save_indexes()
            
        except Exception as e:
            self.logger.error("删除索引失败: owner_id=%s, error=%s", owner_id, e)
            raise RuntimeError(f"删除索引失败: {e}")

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建所有索引"""
        self.logger.info("开始重建索引")
        try:
            # 清空现有索引
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
            
        except Exception as e:
            self.logger.error("索引重建失败: error=%s", e)
            self._indexes.clear()  # 重建失败时清空索引
            self._save_indexes()
            raise RuntimeError(f"索引重建失败: {e}")

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
        """保存索引到存储后端"""
        try:
            data = {
                'types': {field: str(t) for field, t in self._field_types.items()},
                'indexes': dict(self._indexes)
            }
            self._writer.set('.indexes', data)
            
        except Exception as e:
            self.logger.error("保存索引失败: %s", e)
            raise

    def _load_indexes(self) -> None:
        """从存储后端加载索引"""
        try:
            data = self._writer.get('.indexes')
            if data:
                self._indexes = defaultdict(lambda: defaultdict(list))
                for field, field_index in data.get('indexes', {}).items():
                    for value, owner_ids in field_index.items():
                        self._indexes[field][value] = owner_ids
                        
        except Exception as e:
            self.logger.error("加载索引失败: %s", e)
            self._indexes = defaultdict(lambda: defaultdict(list))


