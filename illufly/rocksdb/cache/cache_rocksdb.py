from typing import Any, Optional, Tuple
from pathlib import Path
import logging
from ..index import IndexedRocksDB

class CachedRocksDB:
    """基于 RocksDB 的通用缓存类

    这是一个简单的基于 RocksDB 的缓存类，用于缓存一些常用的数据，
    在并发访问时性能要求较高时可以直接升级为从内存数据库或基于缓存的消息队列服务中获取。
    """
    
    def __init__(self, db: IndexedRocksDB):
        """
        初始化缓存类
        
        :param db: RocksDB 实例
        """
        self.rocksdb = db
        self._cache: dict = {}
        self._logger = logging.getLogger(__name__)

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存中的值
        
        :param key: 缓存键
        :return: 缓存值（如果存在），否则返回 None
        """
        if key in self._cache:
            self._logger.debug(f"从缓存中获取数据: {key}, 缓存值: {self._cache[key]}")
            return self._cache[key]

        # 缓存未命中，从 RocksDB 加载
        value = self.rocksdb[key]
        if value is not None:
            self._cache[key] = value
            self._logger.debug(f"从数据库加载数据并缓存: {key}, 缓存值: {value}")
            return value

        self._logger.debug(f"未找到数据: {key}")
        return None

    def put(self, key: str, value: Any) -> None:
        """
        将数据保存到缓存和 RocksDB 中
        
        :param key: 缓存键
        :param value: 缓存值
        """
        self._cache[key] = value
        self.rocksdb.put(key, value)
        self._logger.debug(f"数据已保存到缓存和数据库: {key}")

    def delete(self, key: str) -> None:
        """
        从缓存和 RocksDB 中删除数据
        
        :param key: 缓存键
        """
        if key in self._cache:
            del self._cache[key]
            self._logger.debug(f"已从缓存中删除数据: {key}")

        self.rocksdb.delete(key)
        self._logger.debug(f"数据已从数据库中删除: {key}")

    def clear_cache(self) -> None:
        """
        清空内存缓存（不清理 RocksDB）
        """
        self._cache.clear()
        self._logger.debug("内存缓存已清空")