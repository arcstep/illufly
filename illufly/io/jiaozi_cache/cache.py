from collections import OrderedDict
import threading
from typing import Any, Optional
from abc import ABC, abstractmethod

class CacheBackend(ABC):
    """缓存后端接口"""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    def put(self, key: str, value: Any) -> None:
        """存入缓存值"""
        pass
    
    @abstractmethod
    def remove(self, key: str) -> None:
        """移除缓存项"""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """清空缓存"""
        pass
    
    @abstractmethod
    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        pass

class LRUCacheBackend(CacheBackend):
    """线程安全的LRU缓存实现"""
    
    def __init__(self, capacity: int):
        if capacity < 0:
            raise ValueError("缓存容量不能为负数")
        self.capacity = capacity
        self._cache = OrderedDict()
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        if self.capacity == 0:
            return None
            
        with self._lock:
            if key not in self._cache:
                return None
            value = self._cache.pop(key)
            self._cache[key] = value
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
                "type": "LRU"
            }