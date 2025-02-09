from typing import Any, Optional, Tuple
from pathlib import Path
import logging
from ..index import IndexedRocksDB

class CachedRocksDB:
    """基于 RocksDB 的键值查询缓存类

    对于系统启动后始终是幂等的函数方法，可以考虑直接使用 lru_cache 来缓存操作结果，
    由于 lru_cache 在数据更新时只能通过清理全局缓存，这是一个针对涉及到键值数据时的补充方案。

    如果键值数据以读为主，并且不需要分布式能力，也可以使用这个模块替代 redis 来使用。

    该缓存支持的场景主要是查询单个键值数据，暂时不提供批量查询和索引查询的缓存。
    在需要索引或其他能力时，可直接通过 self.rocksdb 操作 IndexedRocksDB 的实例。
    为了方便与索引一起使用，self.update_with_indexes 方法可用于同时更新缓存和索引。
    """
    
    def __init__(self, db: IndexedRocksDB):
        """
        初始化缓存类
        """
        self.rocksdb = db
        self._cache: dict = {}
        self._logger = logging.getLogger(__name__)

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存中的值
        """
        if key in self._cache:
            return self._cache[key]

        # 缓存未命中，从 RocksDB 加载
        value = self.rocksdb[key]
        if value is not None:
            self._cache[key] = value
            return value

        self._logger.info(f"未找到数据: {key}")
        return None

    def put(self, key: str, value: Any) -> None:
        """
        将数据保存到缓存和 RocksDB 中
        """
        self._cache[key] = value
        self.rocksdb.put(key, value)

    def delete(self, key: str) -> None:
        """
        从缓存和 RocksDB 中删除数据
        """
        if key in self._cache:
            del self._cache[key]
            self._logger.debug(f"已从缓存中删除数据: {key}")

        self.rocksdb.delete(key)

    def clear_cache(self) -> None:
        """
        清空内存缓存（不清理 RocksDB）
        """
        self._cache.clear()
    
    def update_with_indexes(self, model_name: str, key: str, value: Any) -> None:
        """
        同时更新缓存、键值存储和索引
        """
        self._cache[key] = value
        self.rocksdb.update_with_indexes(model_name, key, value)
