from typing import Generic, TypeVar, Any, Optional, Dict, Callable
from dataclasses import dataclass
import logging
import threading
from collections import OrderedDict
from .base import CacheBackend

T = TypeVar('T')

@dataclass
class CacheEvent:
    """缓存事件数据"""
    key: str
    value: Optional[Any]
    event_type: str  # 'hit', 'miss', 'put', 'remove', 'evict'

class LRUCacheBackend(CacheBackend, Generic[T]):
    """线程安全的LRU缓存实现
    
    与 functools.lru_cache 相比，此实现提供：
    1. 可手动控制缓存内容（更新/失效）
    2. 支持非幂等操作的缓存
    3. 详细的缓存统计和监控
    4. 完整的日志记录
    5. 泛型类型支持
    6. 事件回调机制
    7. 序列化支持
    
    适用场景：
    1. 需要手动更新缓存内容
    2. 需要选择性清除特定缓存
    3. 需要监控缓存性能
    4. 缓存动态变化的数据
    5. 作为组合对象使用
    
    示例：
        >>> cache = LRUCacheBackend[dict](capacity=100)
        >>> cache.put("key1", {"value": 1})
        >>> value = cache.get("key1")
        >>> with cache:  # 支持上下文管理
        ...     cache.put("key2", {"value": 2})
    """
    
    def __init__(
        self, 
        capacity: int,
        logger: Optional[logging.Logger] = None,
        on_hit: Optional[Callable[[CacheEvent], None]] = None,
        on_miss: Optional[Callable[[CacheEvent], None]] = None,
        on_evict: Optional[Callable[[CacheEvent], None]] = None
    ):
        if capacity < 0:
            raise ValueError("缓存容量不能为负数")
            
        self.capacity = capacity
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self.logger = logger or logging.getLogger(__name__)
        self._on_hit = on_hit
        self._on_miss = on_miss
        self._on_evict = on_evict
        self.logger.info("初始化LRU缓存: capacity=%d", capacity)

    def get(self, key: str) -> Optional[T]:
        if self.capacity == 0:
            self._misses += 1
            self._trigger_event('miss', key, None)
            return None

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                self._trigger_event('miss', key, None)
                return None
                
            value = self._cache.pop(key)
            self._cache[key] = value
            self._hits += 1
            self._trigger_event('hit', key, value)
            return value

    def put(self, key: str, value: T) -> None:
        if self.capacity == 0:
            return
            
        with self._lock:
            if key in self._cache:
                self._cache.pop(key)
            elif len(self._cache) >= self.capacity:
                evicted_key, evicted_value = self._cache.popitem(last=False)
                self._trigger_event('evict', evicted_key, evicted_value)
                
            self._cache[key] = value
            self._trigger_event('put', key, value)

    def _trigger_event(self, event_type: str, key: str, value: Optional[T]) -> None:
        """触发缓存事件"""
        event = CacheEvent(key, value, event_type)
        if event_type == 'hit' and self._on_hit:
            self._on_hit(event)
        elif event_type == 'miss' and self._on_miss:
            self._on_miss(event)
        elif event_type == 'evict' and self._on_evict:
            self._on_evict(event)

    def __iter__(self):
        """返回缓存项的迭代器"""
        with self._lock:
            return iter(self._cache.copy().items())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.clear()

    def to_dict(self) -> Dict[str, T]:
        """导出缓存内容"""
        with self._lock:
            return dict(self._cache)

    @classmethod
    def from_dict(cls, data: Dict[str, T], capacity: int) -> 'LRUCacheBackend[T]':
        """从字典创建缓存"""
        cache = cls(capacity)
        for k, v in data.items():
            cache.put(k, v)
        return cache

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