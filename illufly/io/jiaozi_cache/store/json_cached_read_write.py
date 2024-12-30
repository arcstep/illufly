from typing import Generic, TypeVar, Optional, Any, Dict
import logging
from pathlib import Path
from ....config import get_env
from ..cache import LRUCacheBackend, CacheEvent
from .json_buffered_write import WriteBufferedJSONStorage
from .base import StorageBackend

T = TypeVar('T')

class CachedJSONStorage(StorageBackend, Generic[T]):
    """带读写缓存的JSON文件存储
    
    性能特性：
    1. 写入性能：O(1) 内存写入，批量磁盘IO
    2. 读取性能：O(1) 缓存命中，O(log n) 文件读取
    3. 内存占用：可配置的缓存和缓冲区大小
    
    使用建议：
    1. 适用场景：
       - 频繁读写的小型数据
       - 需要持久化的临时数据
       - 对写入延迟不敏感的场景
       
    2. 注意事项：
       - 内存使用会随数据量增长
       - 进程异常退出可能丢失缓冲区数据
       - 多进程访问需要额外同步机制
    """
    
    def __init__(
        self,
        data_dir: Optional[str] = None,
        segment: Optional[str] = None,
        cache_size: Optional[int] = None,
        flush_interval: Optional[int] = None,
        flush_threshold: Optional[int] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.logger = logger or logging.getLogger(__name__)
        
        # 使用环境变量配置，允许参数覆盖
        self._data_dir = Path(data_dir or get_env("JIAOZI_CACHE_STORE_DIR"))
        self._cache_size = cache_size or int(get_env("JIAOZI_CACHE_READ_SIZE"))
        self._flush_interval = flush_interval or int(get_env("JIAOZI_CACHE_FLUSH_INTERVAL"))
        self._flush_threshold = flush_threshold or int(get_env("JIAOZI_CACHE_FLUSH_THRESHOLD"))
        
        # 初始化存储后端
        self._storage = WriteBufferedJSONStorage[T](
            data_dir=str(self._data_dir),
            segment=segment,
            flush_interval=self._flush_interval,
            flush_threshold=self._flush_threshold,
            logger=logger
        )
        
        # 初始化缓存后端
        def on_evict(event: CacheEvent):
            """缓存淘汰回调"""
            self.logger.debug("缓存项被淘汰: key=%s", event.key)
            
        self._cache = LRUCacheBackend[T](
            capacity=self._cache_size,
            logger=logger,
            on_evict=on_evict
        )
        
        self.logger.info(
            "初始化缓存存储: dir=%s, segment=%s, cache_size=%d, "
            "flush_interval=%d, flush_threshold=%d",
            self._data_dir, segment, self._cache_size,
            self._flush_interval, self._flush_threshold
        )

    def get(self, key: str) -> Optional[T]:
        """获取数据，优先从缓存读取"""
        # 1. 先检查写缓冲区（避免脏读）
        value = self._storage.get_from_buffer(key)
        if value is not None:
            return value
            
        # 2. 再检查读缓存
        value = self._cache.get(key)
        if value is not None:
            return value
            
        # 3. 最后从存储读取
        value = self._storage.get(key)
        if value is not None:
            self._cache.put(key, value)
        return value

    def set(self, key: str, value: T) -> None:
        """写入数据到存储和缓存"""
        try:
            self._storage.set(key, value)
            if self._cache.exists(key):
                self._cache.put(key, value)
        except Exception as e:
            self.logger.error("写入失败: key=%s, error=%s", key, e)
            # 确保缓存一致性
            self._cache.remove(key)
            raise

    def delete(self, key: str) -> bool:
        """删除数据"""
        self._cache.remove(key)
        return self._storage.delete(key)

    def clear(self) -> None:
        """清空所有数据"""
        self._cache.clear()
        self._storage.clear()

    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        cache_stats = self._cache.get_stats()
        storage_metrics = self._storage.get_metrics()
        
        return {
            "read_cache": {
                "size": cache_stats["size"],
                "capacity": cache_stats["capacity"],
                "hits": cache_stats["hits"],
                "misses": cache_stats["misses"],
                "hit_rate": cache_stats["hit_rate"]
            },
            "write_buffer": {
                "size": storage_metrics["buffer_size"],
                "dirty_count": storage_metrics["dirty_count"],
                "modify_count": storage_metrics["modify_count"],
                "last_flush": storage_metrics["last_flush"]
            },
            "total_operations": cache_stats["hits"] + cache_stats["misses"] + storage_metrics["modify_count"]
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self) -> None:
        """关闭存储"""
        self._storage.close()
        self._cache.clear()