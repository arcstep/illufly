from collections import OrderedDict
import threading
from typing import Any, Optional
from .base import CacheBackend

class LRUCacheBackend(CacheBackend):
    """线程安全的LRU缓存实现"""
    
    def __init__(self, capacity: int):
        if capacity < 0:
            raise ValueError("缓存容量不能为负数")
        self.capacity = capacity
        self._cache = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        if self.capacity == 0:
            self._misses += 1
            return None
            
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            value = self._cache.pop(key)
            self._cache[key] = value
            self._hits += 1
            return value
    
    def put(self, key: str, value: Any) -> None:
        if self.capacity == 0:
            return
            
        with self._lock:
            if key in self._cache:
                self._cache.pop(key)
            elif len(self._cache) >= self.capacity:
                self._cache.popitem(last=False)
            self._cache[key] = value
    
    def remove(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
    
    def get_stats(self) -> dict:
        with self._lock:
            return {
                "capacity": self.capacity,
                "size": len(self._cache),
                "type": "LRU",
                "hits": self._hits,
                "misses": self._misses
            }