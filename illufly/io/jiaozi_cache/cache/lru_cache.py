from typing import Dict, Any, Optional, Generic, TypeVar, List, Callable
from collections import OrderedDict
import logging
from datetime import datetime
import time
import threading

T = TypeVar('T')

class CacheEvent:
    """缓存事件"""
    def __init__(self, key: str, value: Any):
        self.key = key
        self.value = value
        self.timestamp = datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "key": self.key,
            "value": self.value,
            "timestamp": self.timestamp.isoformat()
        }

class LRUCacheBackend(Generic[T]):
    def __init__(
        self,
        capacity: int,
        logger: Optional[logging.Logger] = None,
        on_evict: Optional[Callable[[CacheEvent], None]] = None
    ):
        self._capacity = capacity
        self._cache: OrderedDict[str, T] = OrderedDict()
        self.logger = logger or logging.getLogger(__name__)
        self._on_evict = on_evict
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._last_eviction = None
        self._hit_times: List[float] = []
        self._miss_times: List[float] = []
        self._max_time_samples = 1000
        self._lock = threading.RLock()  # 使用可重入锁
        
        self.logger.info(f"初始化LRU缓存: capacity={capacity}")

    def get(self, key: str) -> Optional[T]:
        """获取缓存项"""
        start_time = time.perf_counter()
        
        with self._lock:
            try:
                value = self._cache.get(key)
                if value is not None:
                    self._cache.move_to_end(key)
                    self._hits += 1
                    hit_time = time.perf_counter() - start_time
                    if len(self._hit_times) >= self._max_time_samples:
                        self._hit_times.pop(0)
                    self._hit_times.append(hit_time)
                    return value
                
                self._misses += 1
                miss_time = time.perf_counter() - start_time
                if len(self._miss_times) >= self._max_time_samples:
                    self._miss_times.pop(0)
                self._miss_times.append(miss_time)
                return None
                
            except Exception as e:
                self.logger.error(f"缓存读取错误: {e}")
                return None

    def set(self, key: str, value: T) -> None:
        """设置缓存项"""
        with self._lock:
            try:
                if len(self._cache) >= self._capacity:
                    self._evict()
                    
                self._cache[key] = value
                self._cache.move_to_end(key)
                
            except Exception as e:
                self.logger.error(f"缓存写入错误: {e}")

    def _evict(self):
        """淘汰最旧的项目"""
        if self._cache:
            key, value = self._cache.popitem(last=False)
            self._evictions += 1
            self._last_eviction = datetime.now()
            
            if self._on_evict:
                try:
                    self._on_evict(CacheEvent(key, value))
                except Exception as e:
                    self.logger.error(f"缓存淘汰回调错误: {e}")

    def delete(self, key: str) -> None:
        """删除缓存项"""
        with self._lock:
            try:
                if key in self._cache:
                    self._cache.pop(key)
            except Exception as e:
                self.logger.error(f"缓存删除错误: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "capacity": self._capacity,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total > 0 else 0.0,
                "evictions": self._evictions,
                "last_eviction": self._last_eviction,
                "avg_hit_time": (sum(self._hit_times) / len(self._hit_times) * 1000) if self._hit_times else 0.0,
                "avg_miss_time": (sum(self._miss_times) / len(self._miss_times) * 1000) if self._miss_times else 0.0
            }

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            self._hit_times.clear()
            self._miss_times.clear()
            self.logger.info("缓存已清空")