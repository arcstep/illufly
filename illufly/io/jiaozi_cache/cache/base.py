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
    def set(self, key: str, value: Any) -> None:
        """存入缓存值"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> None:
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
