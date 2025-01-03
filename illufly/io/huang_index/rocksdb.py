from typing import Optional, Any, List, Dict, Set, Iterator, Tuple, Union
from rocksdict import Rdict, Options, ColumnFamily, ReadOptions
import msgpack
from pathlib import Path

from ...config import get_env
from .patterns import KeyPattern, RocksDBConfig

class RocksDB:
    """RocksDB存储后端
    
    提供了对RocksDB的基本CRUD操作封装,支持:
    - 多列族(collection)管理
    - 键模式验证
    - 范围查询和前缀扫描
    - 序列化/反序列化
    
    基本用法:
    ```python
    # 初始化数据库
    db = RocksDB("/path/to/db")
    
    # 创建集合
    db.set_collection_options("users", {})
    
    # 写入数据
    db.set("users", "user:1", {"name": "张三", "age": 18})
    db.set("users", "user:2", {"name": "李四", "age": 20})
    
    # 读取数据
    user = db.get("users", "user:1")
    
    # 范围查询示例
    # 1. 按前缀查询所有用户
    for key in db.iter_keys("users", prefix="user:"):
        user = db.get("users", key)
        print(f"{key}: {user}")
        
    # 2. 范围查询年龄20-30的用户
    for key in db.iter_keys("users", start="user:20", end="user:30"):
        user = db.get("users", key)
        print(f"{key}: {user}")
        
    # 3. 获取前10个用户
    for key in db.iter_keys("users", prefix="user:", limit=10):
        user = db.get("users", key)
        print(f"{key}: {user}")
        
    # 4. 获取第一个和最后一个用户
    first_user = db.first("users")
    last_user = db.last("users")
    
    # 5. 使用pattern匹配键
    # 获取所有user:开头的键值对
    pattern = KeyPattern("user:{id}")
    all_users = db.all("users", pattern=pattern)
    
    # 获取第一个和最后一个匹配pattern的键值对
    first_user = db.first("users", pattern=pattern)
    last_user = db.last("users", pattern=pattern)
    
    # 删除数据
    db.delete("users", "user:1")
    
    # 关闭数据库
    db.close()
    ```
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """初始化RocksDB"""
        self._db_path = Path(db_path or get_env("ROCKSDB_BASE_DIR"))
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用 RocksDBConfig 创建默认配置
        self._config = RocksDBConfig("default")
        
        # 使用配置对象获取默认选项
        self._default_cf_options = self._config.default_options
        
        self._collection_configs: Dict[str, Options] = {}
        self._collections: Dict[str, ColumnFamily] = {}
        self._db = self._open_db()
        
        # 设置基础序列化方法
        self._db.set_dumps(msgpack.packb)
        self._db.set_loads(msgpack.unpackb)
        
    def _open_db(self) -> Rdict:
        """打开数据库"""
        opts = self._config.create_options(self._default_cf_options)
        
        # 设置写缓冲区管理器
        opts.set_write_buffer_manager(self._config.write_buffer_manager)
        
        # 打开数据库
        db = Rdict(str(self._db_path), opts)
        
        # 确保默认列族存在
        if 'default' not in Rdict.list_cf(str(self._db_path)):
            db.create_cf('default', self._config.create_options(self._default_cf_options))
            
        return db
        
    def make_key(self, pattern: KeyPattern, **kwargs) -> str:
        """构造键"""
        return KeyPattern.make_key(pattern, **kwargs)
        
    def validate_key(self, key: str) -> bool:
        """验证键是否合法"""
        return KeyPattern.validate_key(key)
        
    def list_collections(self) -> List[str]:
        """列出所有集合（列族）"""
        return Rdict.list_cf(str(self._db_path))
        
    def set_collection_options(self, name: str, options: Dict[str, Any]) -> None:
        """设置集合（列族）配置"""
        if name not in self._collections:
            opts = self._config.create_options(options)
            self._collections[name] = self._db.create_column_family(name, opts)
            self._collection_configs[name] = options
        else:
            raise ValueError(f"集合 {name} 已存在")
            
    def get(self, collection: str, key: str) -> Optional[Any]:
        """获取值
        
        Args:
            collection: 集合名称
            key: 键名
            
        Returns:
            Optional[Any]: 键对应的值,如果不存在则返回None
            
        Raises:
            ValueError: 键格式非法时抛出
        """
        if not self.validate_key(key):
            raise ValueError(f"非法键格式: {key}")
            
        cf = self.get_collection(collection)
        value = cf.get(key.encode())
        return value  # 不需要手动反序列化，rocksdict 会使用我们设置的 msgpack.unpackb
        
    def set(self, collection: str, key: str, value: Any) -> None:
        """设置值
        
        Args:
            collection: 集合名称
            key: 键名
            value: 要存储的值
            
        Raises:
            ValueError: 键格式非法时抛出
        """
        if not self.validate_key(key):
            raise ValueError(f"非法键格式: {key}")
            
        cf = self.get_collection(collection)
        cf[key.encode()] = value  # 不需要手动序列化，rocksdict 会使用我们设置的 msgpack.packb
        
    def iter_keys(self,
                 collection: str,
                 pattern: Optional[KeyPattern] = None,
                 prefix: Optional[str] = None,
                 start: Optional[str] = None,
                 end: Optional[str] = None,
                 limit: Optional[int] = None) -> Iterator[str]:
        """迭代键"""
        cf = self.get_collection(collection)
        read_opts = ReadOptions()
        
        # 获取迭代器
        it = cf.iter(read_opts)
        count = 0
        
        try:
            # 设置起始位置
            if prefix:
                it.seek(prefix.encode())  # 转换为字节串
            elif start:
                it.seek(start.encode())
            else:
                it.seek_to_first()
                
            # 迭代所有键
            while it.valid():
                key_bytes = it.key()
                key = key_bytes.decode() if isinstance(key_bytes, bytes) else key_bytes
                
                # 检查前缀匹配
                if prefix and not key.startswith(prefix):
                    break
                    
                # 检查是否超过结束位置
                if end and key >= end:
                    break
                    
                if limit and count >= limit:
                    break
                    
                if pattern and not self.validate_key(key):
                    it.next()
                    continue
                    
                yield key
                count += 1
                it.next()
                
        finally:
            del it
            
    def all(self, collection: str, prefix: Optional[str] = None, 
            start: Optional[str] = None, end: Optional[str] = None) -> List[Tuple[str, Any]]:
        """获取所有键值对
        
        Args:
            collection: 集合名称
            prefix: 前缀匹配
            start: 范围开始
            end: 范围结束
        """
        return [(k, self.get(collection, k)) 
                for k in self.iter_keys(collection, prefix=prefix, start=start, end=end)]
        
    def first(self, collection: str, prefix: Optional[str] = None) -> Optional[Tuple[str, Any]]:
        """获取第一个键值对"""
        for key in self.iter_keys(collection, prefix=prefix, limit=1):
            return key, self.get(collection, key)
        return None
        
    def last(self, collection: str, prefix: Optional[str] = None) -> Optional[Tuple[str, Any]]:
        """获取最后一个键值对"""
        for key in self.iter_keys(collection, prefix=prefix, reverse=True, limit=1):
            return key, self.get(collection, key)
        return None
        
    def delete(self, collection: str, key: str) -> None:
        """删除键值对
        
        Args:
            collection: 集合名称
            key: 要删除的键
            
        Raises:
            ValueError: 键格式非法时抛出
        """
        if not self.validate_key(key):
            raise ValueError(f"非法键格式: {key}")
            
        cf = self.get_collection(collection)
        del cf[key.encode()]
        
    def drop_collection(self, name: str) -> None:
        """删除集合（列族）"""
        if name in self._collections:
            self._db.drop_column_family(name)
            del self._collections[name]
            if name in self._collection_configs:
                del self._collection_configs[name]
            
    def drop_all(self) -> None:
        """删除所有集合（列族）"""
        for name in list(self._collections.keys()):
            self.drop_collection(name)
            
    def close(self) -> None:
        """关闭数据库"""
        if hasattr(self, '_db'):
            self._db.close()
            del self._db
        if hasattr(self, '_config'):
            del self._config
        
    def get_statistics(self) -> Dict[str, Any]:
        """获取数据库基本信息
        
        Returns:
            Dict[str, Any]: 包含以下统计信息：
                - disk_usage: 数据库文件占用的磁盘空间（字节）
                - num_entries: 数据库中的总键值对数量
                - collections: 列族统计
                    - {collection_name}: 每个列族的统计
                        - num_entries: 该列族的键值对数量
                        - options: 该列族的配置选项
                - cache: 全局缓存统计
                    - block_cache: 块缓存统计
                        - capacity: 配置的容量（字节）
                        - usage: 当前使用量（字节）
                        - pinned_usage: 固定内存使用量（字节）
                    - row_cache: 行缓存统计（同上）
                - write_buffer: 全局写缓冲区统计
                    - buffer_size: 缓冲区大小（字节）
                    - usage: 当前使用量（字节）
                    - enabled: 是否启用
                - global_config: 全局配置
                    - memtable: 内存表配置
                    - compression: 压缩配置
                    - performance: 性能相关配置
        """
        stats = {}
        try:
            # 获取数据库文件大小
            db_path = Path(self._db_path)
            if db_path.exists():
                stats["disk_usage"] = sum(f.stat().st_size for f in db_path.rglob('*') if f.is_file())
            
            # 按列族统计
            stats["collections"] = {}
            total_keys = 0
            
            for collection in self.list_collections():
                cf = self.get_collection(collection)
                # 计算该列族的键数量
                count = sum(1 for _ in cf.keys())
                total_keys += count
                
                # 获取列族配置
                cf_config = self._collection_configs.get(collection, self._default_cf_options)
                
                # 记录列族统计
                stats["collections"][collection] = {
                    "num_entries": count,
                    "options": {
                        "compression_type": str(cf_config.get('compression_type', self._config.compression_type)),
                        "write_buffer_size": cf_config.get('write_buffer_size', self._config.write_buffer_size),
                        "max_write_buffer_number": cf_config.get('max_write_buffer_number', 
                                                               self._config.max_write_buffer_number),
                        "min_write_buffer_number": cf_config.get('min_write_buffer_number',
                                                               self._config.min_write_buffer_number),
                        "level0_file_num_compaction_trigger": cf_config.get('level0_file_num_compaction_trigger',
                                                                          self._config.level0_file_num_compaction_trigger)
                    }
                }
            
            stats["num_entries"] = total_keys
            
            # 全局缓存统计
            stats["cache"] = {
                "block_cache": {
                    "capacity": self._config.block_cache_size,
                    "usage": self._config.block_cache.get_usage(),
                    "pinned_usage": self._config.block_cache.get_pinned_usage()
                },
                "row_cache": {
                    "capacity": self._config.row_cache_size,
                    "usage": self._config.row_cache.get_usage(),
                    "pinned_usage": self._config.row_cache.get_pinned_usage()
                }
            }
            
            # 全局写缓冲区统计
            write_buffer_manager = self._config.write_buffer_manager
            stats["write_buffer"] = {
                "buffer_size": write_buffer_manager.get_buffer_size(),
                "usage": write_buffer_manager.get_usage(),
                "enabled": write_buffer_manager.enabled()
            }
            
            # 全局配置
            stats["global_config"] = {
                "memtable": {
                    "write_buffer_size": self._config.write_buffer_size,
                    "max_write_buffer_number": self._config.max_write_buffer_number,
                    "min_write_buffer_number": self._config.min_write_buffer_number
                },
                "compression": {
                    "type": str(self._config.compression_type)
                },
                "performance": {
                    "level0_file_num_compaction_trigger": self._config.level0_file_num_compaction_trigger,
                    "max_background_jobs": self._config.max_background_jobs,
                    "enable_pipelined_write": self._config.enable_pipelined_write
                }
            }
                
        except Exception as e:
            stats["error"] = str(e)
            
        return stats

    def get_collection(self, name: str) -> Rdict:
        """获取集合（列族）"""
        if name not in self._collections:
            # 检查列族是否已存在
            existing_cfs = Rdict.list_cf(str(self._db_path))
            if name in existing_cfs:
                self._collections[name] = self._db.get_column_family(name)
            else:
                # 如果集合不存在，创建它
                opts = self._config.create_options(self._default_cf_options)
                self._collections[name] = self._db.create_column_family(name, opts)
        return self._collections[name]
