from typing import Dict, Any, List, Callable, Optional, Tuple, Union
from collections import defaultdict
import json
import logging
from pathlib import Path
from pydantic import BaseModel
from datetime import datetime

from ....config import get_env
from .index_backend import IndexBackend, Indexable
from .index_config import IndexConfig
from ..store import CachedJSONStorage, StorageStrategy, TimeSeriesGranularity

class HashIndexBackend(IndexBackend):
    """基于哈希的索引后端实现
    
    典型应用场景：
    
    1. 用户系统中的多字段索引：
    ```python
    # 初始化用户索引
    user_index = HashIndexBackend(
        segment="users",
        field_types={
            "id": str,
            "email": str,
            "status": str,
            "tags": List[str]
        }
    )
    
    # 多个用户可能有相同的状态
    user_index.update_index(
        {"id": "001", "email": "alice@example.com", "status": "active"},
        key="user_001"
    )
    user_index.update_index(
        {"id": "002", "email": "bob@example.com", "status": "active"},
        key="user_002"
    )
    
    # 查询所有活跃用户
    active_users = user_index.find_with_index("status", "active")
    # 返回: ["user_001", "user_002"]
    ```
    
    2. 商品标签系统：
    ```python
    # 初始化商品索引
    product_index = HashIndexBackend(
        segment="products",
        field_types={
            "id": str,
            "category": str,
            "tags": List[str],
            "price.range": str  # 价格区间作为索引
        }
    )
    
    # 一个商品可以有多个标签
    product_index.update_index(
        {
            "id": "p001",
            "category": "electronics",
            "tags": ["phone", "5G", "android"],
            "price.range": "1000-2000"
        },
        key="product_001"
    )
    
    # 查找所有 5G 手机
    phones_5g = product_index.find_with_index("tags", "5G")
    # 返回包含 "5G" 标签的所有商品
    ```
    
    3. 地址系统（嵌套字段）：
    ```python
    # 初始化地址索引
    address_index = HashIndexBackend(
        segment="addresses",
        field_types={
            "user_id": str,
            "address.city": str,
            "address.country": str,
            "type": str
        }
    )
    
    # 同一个城市可能有多个地址
    address_index.update_index(
        {
            "user_id": "001",
            "address": {"city": "Shanghai", "country": "China"},
            "type": "home"
        },
        key="addr_001"
    )
    address_index.update_index(
        {
            "user_id": "002",
            "address": {"city": "Shanghai", "country": "China"},
            "type": "office"
        },
        key="addr_002"
    )
    
    # 查找特定城市的所有地址
    shanghai_addresses = address_index.find_with_index("address.city", "Shanghai")
    # 返回: ["addr_001", "addr_002"]
    ```
    
    4. 更新场景（说明索引更新机制）：
    ```python
    # 用户更改状态
    user_index.update_index(
        {"id": "001", "email": "alice@example.com", "status": "inactive"},
        key="user_001"
    )
    # 内部过程：
    # 1. 通过 index@user_001 找到所有旧的索引路径
    # 2. 从 reverse@status:active 中移除 user_001
    # 3. 在 reverse@status:inactive 中添加 user_001
    
    # 此时查询活跃用户
    active_users = user_index.find_with_index("status", "active")
    # 返回: ["user_002"]  # user_001 已经不在活跃列表中
    ```
    
    注意事项：
    1. 索引键的唯一性：
       - 正向索引（index@key）确保每个对象的索引路径可追踪
       - 反向索引（reverse@path）支持多个对象共享相同的值
    
    2. 更新开销：
       - 每次更新都需要维护双向索引
       - 对于频繁更新的场景，需要考虑性能影响
    
    3. 存储效率：
       - 每个索引字段都会创建额外的存储项
       - 多值字段（如标签）会创建多个索引项
    """
    
    def __init__(
        self, 
        field_types: Dict[str, Any] = None,
        config: Optional[IndexConfig] = None,
        data_dir: str = None,
        segment: str = None,
        cache_size: int = None,
        flush_interval: Optional[int] = None,
        flush_threshold: Optional[int] = None,
        strategy: StorageStrategy = None,
        time_granularity: TimeSeriesGranularity = None,
        partition_count: Optional[int] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """初始化哈希索引后端"""
        super().__init__(field_types=field_types, config=config)
        
        # 使用带缓冲的存储后端
        self._storage = CachedJSONStorage(
            data_dir=data_dir,
            segment=segment or "index.json",
            cache_size=cache_size or 100000,
            flush_interval=flush_interval,
            flush_threshold=flush_threshold,
            strategy=strategy or StorageStrategy.SHARED,
            time_granularity=time_granularity or TimeSeriesGranularity.MONTHLY,
            partition_count=partition_count or 32,
            logger=logger
        )
        
        self.logger = logger or logging.getLogger(__name__)
        self._index_key_prefix = "index@"  # 正向索引前缀：key -> index_paths
        self._reverse_key_prefix = "reverse@"  # 反向索引前缀：index_path -> keys
    
    def _get_index_key(self, key: str) -> str:
        """获取正向索引键（key -> index_paths）"""
        return f"{self._index_key_prefix}{key}"
    
    def _get_reverse_key(self, index_path: str) -> str:
        """获取反向索引键（index_path -> keys）"""
        return f"{self._reverse_key_prefix}{index_path}"
    
    def save_indexes(self) -> None:
        """保存字段类型信息"""
        try:
            # 只需要保存字段类型信息
            self._storage.set('meta:field_types', {
                field_path: str(t) for field_path, t in self._field_types.items()
            })
            self.logger.info("字段类型信息保存成功")
        except Exception as e:
            self.logger.error("保存字段类型信息失败: %s", e)
            raise RuntimeError(f"保存字段类型信息失败: {e}")

    def load_indexes(self) -> None:
        """加载字段类型信息"""
        try:
            types = self._storage.get('meta:field_types')
            if types:
                self._field_types.update(types)
            self.logger.info("字段类型信息加载成功")
        except Exception as e:
            self.logger.error("加载字段类型信息失败: %s", e)
            raise RuntimeError(f"加载字段类型信息失败: {e}")

    def add_to_index(self, field: str, value: Any, key: str) -> None:
        """添加索引项
        
        Args:
            field: 字段路径（可能是嵌套路径，如 'address.city'）
            value: 字段值
            key: 数据键
        """
        if value is None:
            return
            
        # 处理列表类型
        if isinstance(value, list):
            for item in value:
                if item is not None:
                    index_path = f"{field}:{item}"
                    self._add_to_index_path(index_path, key)
            return
            
        # 处理可索引对象和其他类型
        if isinstance(value, Indexable):
            index_path = f"{field}:{value.to_index_key()}"
        else:
            index_path = f"{field}:{value}"
            
        self._add_to_index_path(index_path, key)

    def _add_to_index_path(self, index_path: str, key: str) -> None:
        """添加单个索引路径，同时维护正向和反向索引
        
        Args:
            index_path: 索引路径（如 'address.city:Chicago'）
            key: 数据键
        """
        # 1. 更新反向索引（index_path -> keys）
        reverse_key = self._get_reverse_key(index_path)
        keys = self._storage.get(reverse_key)
        if keys is None:
            keys = {key}
        else:
            keys = set(keys) if isinstance(keys, (list, set)) else {keys}
            keys.add(key)
        self._storage.set(reverse_key, keys)
        
        # 2. 更新正向索引（key -> index_paths）
        index_key = self._get_index_key(key)
        paths = self._storage.get(index_key) or []
        if not isinstance(paths, list):
            paths = [paths] if paths else []
        if index_path not in paths:
            paths.append(index_path)
            self._storage.set(index_key, paths)

    def clear_indexes(self) -> None:
        """清空所有索引"""
        try:
            # 获取所有字段
            for field_path in self._field_types:
                field_key = self._make_field_key(field_path)
                values = self._storage.get(field_key) or []
                
                # 删除每个字段的所有索引
                for value in values:
                    index_key = self._make_index_key(field_path, value)
                    self._storage.delete(index_key)
                
                # 删除字段元数据
                self._storage.delete(field_key)
                
            self.logger.info("索引已清空")
            
        except Exception as e:
            self.logger.error("清空索引失败: %s", e)
            raise RuntimeError(f"清空索引失败: {e}")

    def get_field_index_size(self, field_path: str) -> int:
        """获取指定字段的索引大小"""
        field_key = self._make_field_key(field_path)
        values = self._storage.get(field_key) or []
        return len(values)

    def remove_from_index(self, key: str) -> None:
        """从索引中删除指定键的所有索引项"""
        index_key = self._get_index_key(key)
        paths = self._storage.get(index_key)
        if not paths:
            return
            
        # 删除所有索引路径
        for path in paths:
            value = self._storage.get(path)
            if value is None:
                continue
                
            if isinstance(value, (list, set)):
                value = set(value) - {key}
                if value:
                    self._storage.set(path, value)
                else:
                    self._storage.delete(path)
            elif value == key:
                self._storage.delete(path)
        
        # 删除索引路径记录
        self._storage.delete(index_key)

    def find_with_tag(self, field_path: str, tag: str) -> List[str]:
        """实现标签查询"""
        index_key = self._make_index_key(field_path, str(tag))
        return self._storage.get(index_key) or []

    def find_with_value(self, field_path: str, value: Any) -> List[str]:
        """实现常规值查询"""
        index_key = self._make_index_key(field_path, str(value))
        return self._storage.get(index_key) or []

    def find_with_root_object(self, model: BaseModel) -> List[str]:
        """实现根对象查询"""
        query_json = model.model_dump_json()
        results = []
        
        field_key = self._make_field_key(".")
        values = self._storage.get(field_key) or []
        
        for value in values:
            index_key = self._make_index_key(".", value)
            keys = self._storage.get(index_key) or []
            for key in keys:
                if self._storage.get(key).model_dump_json() == query_json:
                    results.append(key)
                    
        return results

    def has_index(self, field_path: str) -> bool:
        """检查字段是否已建立索引"""
        if field_path not in self._field_types:
            self.logger.error("字段未定义索引类型: %s", field_path)
            return False

        field_key = self._make_field_key(field_path)
        values = self._storage.get(field_key) or []
        exists = len(values) > 0
        
        self.logger.debug("检查索引是否存在: field_path=%s, exists=%s", field_path, exists)
        return exists

    def get_index_size(self) -> int:
        """获取索引大小（索引项数量）"""
        total = 0
        for field_path in self._field_types:
            total += self.get_field_index_size(field_path)
        return total

    def get_index_memory_usage(self) -> int:
        """估算索引内存使用量（字节）"""
        # 直接返回存储后端的内存使用量
        return self._storage.get_memory_usage()

    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建所有索引"""
        self.logger.info("开始重建索引")
        try:
            # 清空现有索引
            self.clear_indexes()
            
            # 重建索引
            count = 0
            for key, data in data_iterator():
                # 为每个字段创建索引
                for field_path in self._field_types:
                    value = self.extract_value_from_path(
                        data, 
                        self._parse_field_path(field_path)
                    )
                    if value is None:
                        continue
                        
                    if isinstance(value, list):
                        for item in value:
                            self.add_to_index(field_path, item, key)
                    else:
                        self.add_to_index(field_path, value, key)
                        
                count += 1
                if count % 1000 == 0:
                    self.logger.info("重建进度: %d 条记录已处理", count)
                    
            self._stats["last_rebuild"] = datetime.now()
            self.logger.info("索引重建完成: 共处理 %d 条记录", count)
            
        except Exception as e:
            self.logger.error("索引重建失败: %s", e)
            self.clear_indexes()
            raise RuntimeError(f"索引重建失败: {e}")

    def update_index(self, data: Any, key: str) -> None:
        """更新索引"""
        # 1. 获取旧的索引路径
        index_key = self._get_index_key(key)
        old_paths = self._storage.get(index_key) or []
        
        # 2. 从反向索引中删除旧的关联
        for path in old_paths:
            reverse_key = self._get_reverse_key(path)
            keys = self._storage.get(reverse_key)
            if keys:
                if isinstance(keys, (list, set)):
                    keys = set(keys) - {key}
                    if keys:
                        self._storage.set(reverse_key, keys)
                    else:
                        self._storage.delete(reverse_key)
                elif keys == key:
                    self._storage.delete(reverse_key)
        
        # 3. 删除旧的正向索引
        self._storage.delete(index_key)
        
        # 4. 创建新的索引
        for field_path in self._field_types.keys():
            value, _ = self.extract_and_convert_value(data, field_path)
            if value is not None:
                self.add_to_index(field_path, value, key)

    def find_with_index(self, field: str, value: Any) -> List[str]:
        """通过索引查找数据"""
        field_type = self._field_types.get(field)
        if field_type is None:
            return []
            
        # 生成索引路径
        if isinstance(value, Indexable):
            index_path = f"{field}:{value.to_index_key()}"
        elif field_type == List[str] and isinstance(value, str):
            index_path = f"{field}:{value}"
        else:
            index_path = f"{field}:{value}"
            
        # 从反向索引中获取键列表
        reverse_key = self._get_reverse_key(index_path)
        keys = self._storage.get(reverse_key)
        if keys is None:
            return []
        return list(keys) if isinstance(keys, (list, set)) else [keys]


