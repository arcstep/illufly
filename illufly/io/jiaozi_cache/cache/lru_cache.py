import logging
import threading
from collections import OrderedDict
from typing import Any, Optional
from .base import CacheBackend

class LRUCacheBackend(CacheBackend):
    """线程安全的LRU缓存实现
    
    与 functools.lru_cache 相比，此实现提供：
    1. 可手动控制缓存内容（更新/失效）
    2. 支持非幂等操作的缓存
    3. 详细的缓存统计和监控
    4. 完整的日志记录
    
    适用场景：
    1. 需要手动更新缓存内容
    2. 需要选择性清除特定缓存
    3. 需要监控缓存性能
    4. 缓存动态变化的数据
    
    示例：
        >>> cache = LRUCacheBackend(capacity=100)
        >>> cache.put("key1", "value1")
        >>> value = cache.get("key1")
        >>> cache.remove("key1")  # 手动使缓存失效
        >>> stats = cache.get_stats()  # 获取性能统计
    
    Args:
        capacity (int): 缓存容量，0表示禁用缓存
        logger (Optional[logging.Logger]): 自定义日志记录器
    
    Attributes:
        capacity (int): 缓存容量
        _cache (OrderedDict): 内部缓存存储
        _hits (int): 缓存命中次数
        _misses (int): 缓存未命中次数
        
    Thread Safety:
        所有方法都通过锁机制确保线程安全
    """
    
    def __init__(self, capacity: int, logger=None):
        if capacity < 0:
            raise ValueError("缓存容量不能为负数")
            
        self.capacity = capacity
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self.logger = logger or logging.getLogger(__name__)
        self.logger.info("初始化LRU缓存: capacity=%d", capacity)
    
    def get(self, key: str) -> Optional[Any]:
        if self.capacity == 0:
            self._misses += 1
            self.logger.debug("缓存容量为0，直接返回None: key=%s", key)
            return None

        with self._lock:
            self.logger.debug("尝试获取缓存: key=%s", key)
            if key not in self._cache:
                self._misses += 1
                self.logger.debug("缓存未命中: key=%s, misses=%d", key, self._misses)
                return None
                
            value = self._cache.pop(key)
            self._cache[key] = value
            self._hits += 1
            
            hit_rate = self._hits / (self._hits + self._misses) * 100
            self.logger.debug("缓存命中: key=%s, value=%s, hits=%d, hit_rate=%.2f%%", 
                            key, value, self._hits, hit_rate)
            return value
    
    def put(self, key: str, value: Any) -> None:
        if self.capacity == 0:
            self.logger.debug("缓存容量为0，跳过写入: key=%s", key)
            return
            
        with self._lock:
            self.logger.debug("写入缓存: key=%s, value=%s", key, value)
            
            if key in self._cache:
                self._cache.pop(key)
                self.logger.debug("更新现有键: key=%s", key)
            elif len(self._cache) >= self.capacity:
                removed_key, _ = self._cache.popitem(last=False)
                self.logger.debug("缓存已满，移除最旧项: removed_key=%s", removed_key)
                
            self._cache[key] = value
            self.logger.debug("缓存状态: size=%d/%d", len(self._cache), self.capacity)
    
    def remove(self, key: str) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.pop(key)
                self.logger.info("从缓存中移除: key=%s", key)
            else:
                self.logger.debug("要移除的键不存在: key=%s", key)
    
    def clear(self) -> None:
        with self._lock:
            size = len(self._cache)
            self._cache.clear()
            self.logger.info("清空缓存: cleared_items=%d", size)
    
    def get_stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            
            stats = {
                "capacity": self.capacity,
                "size": len(self._cache),
                "type": "LRU",
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.2f}%"
            }
            
            self.logger.debug("缓存统计: %s", stats)
            return stats