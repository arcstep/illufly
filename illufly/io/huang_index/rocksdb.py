from typing import Optional, Any, List, Dict, Set, Iterator, Tuple, Union
from rocksdict import (
    Rdict, Options, ColumnFamily, ReadOptions, DBCompressionType,
    Cache, BlockBasedOptions, WriteBufferManager
)
import msgpack
import os
from pathlib import Path
from enum import Enum
import re

from ...config import get_env

class KeyPattern(Enum):
    """键模式枚举"""
    PREFIX_ID = "prefix:id"  
    PREFIX_ID_SUFFIX = "prefix:id:suffix"
    PREFIX_INFIX_ID = "prefix:infix:id"
    PREFIX_INFIX_ID_SUFFIX = "prefix:infix:id:suffix"
    PREFIX_PATH_VALUE = "prefix:path:value"
    PREFIX_INFIX_PATH_VALUE = "prefix:infix:path:value"

class RocksDB:
    """RocksDB存储后端"""
    
    def __init__(self, db_path: Optional[str] = None):
        """初始化RocksDB"""
        self._db_path = Path(db_path or get_env("ROCKSDB_BASE_DIR"))
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 创建缓存
        block_cache_size = int(get_env("ROCKSDB_BLOCK_CACHE_SIZE")) * 1024 * 1024
        row_cache_size = int(get_env("ROCKSDB_ROW_CACHE_SIZE")) * 1024 * 1024
        self._block_cache = Cache(block_cache_size)
        self._row_cache = Cache(row_cache_size)
        
        # 获取压缩类型
        compression_map = {
            'none': DBCompressionType.none(),
            'snappy': DBCompressionType.snappy(),
            'lz4': DBCompressionType.lz4(),
            'zstd': DBCompressionType.zstd(),
            'bz2': DBCompressionType.bz2(),
            'lz4hc': DBCompressionType.lz4hc(),
            'zlib': DBCompressionType.zlib()
        }
        compression_type = compression_map.get(
            get_env("ROCKSDB_DEFAULT_CF_COMPRESSION").lower(),
            DBCompressionType.lz4()  # 默认使用 lz4
        )
        
        # 默认配置
        self._default_cf_options = {
            'compression_type': compression_type,  # 使用配置的压缩类型
            'write_buffer_size': int(get_env("ROCKSDB_DEFAULT_CF_WRITE_BUFFER_SIZE")) * 1024 * 1024,
            'max_write_buffer_number': int(get_env("ROCKSDB_DEFAULT_CF_MAX_WRITE_BUFFER_NUMBER")),
            'min_write_buffer_number': int(get_env("ROCKSDB_MIN_WRITE_BUFFER_NUMBER")),
            'level0_file_num_compaction_trigger': int(get_env("ROCKSDB_LEVEL0_FILE_NUM_COMPACTION_TRIGGER")),
            'max_background_jobs': int(get_env("ROCKSDB_MAX_BACKGROUND_JOBS")),
            'enable_pipelined_write': bool(get_env("ROCKSDB_ENABLE_PIPELINED_WRITE"))  # 直接使用布尔值
        }
        
        self._collection_configs: Dict[str, Options] = {}
        self._collections: Dict[str, ColumnFamily] = {}
        self._db = self._open_db()
        
        # 使用 MessagePack 进行序列化
        self._db.set_dumps(msgpack.packb)
        self._db.set_loads(msgpack.unpackb)
        
    def _open_db(self) -> Rdict:
        """打开数据库"""
        opts = self._create_options(self._default_cf_options)
        
        # 创建写缓冲区管理器
        buffer_size = int(get_env("ROCKSDB_WRITE_BUFFER_SIZE")) * 1024 * 1024
        write_buffer_manager = WriteBufferManager.new_write_buffer_manager_with_cache(
            buffer_size, True, self._block_cache
        )
        opts.set_write_buffer_manager(write_buffer_manager)
        
        # 打开数据库
        db = Rdict(str(self._db_path), opts)
        
        # 确保默认列族存在
        if 'default' not in Rdict.list_cf(str(self._db_path)):
            db.create_cf('default', self._create_options(self._default_cf_options))
            
        return db
        
    def _create_options(self, config: Dict[str, Any]) -> Options:
        """创建Options对象"""
        opts = Options()
        opts.create_if_missing(True)
        
        # 处理压缩类型
        if 'compression_type' in config:
            compression_map = {
                'none': DBCompressionType.none(),
                'snappy': DBCompressionType.snappy(),
                'lz4': DBCompressionType.lz4(),
                'zstd': DBCompressionType.zstd(),
                'bz2': DBCompressionType.bz2(),
                'lz4hc': DBCompressionType.lz4hc(),
                'zlib': DBCompressionType.zlib()
            }
            compression_type = compression_map.get(
                config['compression_type'].lower() if isinstance(config['compression_type'], str) else 'lz4',
                DBCompressionType.lz4()  # 默认使用 lz4
            )
            opts.set_compression_type(compression_type)
        
        # 基本选项设置
        if 'write_buffer_size' in config:
            opts.set_write_buffer_size(config['write_buffer_size'])
        if 'max_write_buffer_number' in config:
            opts.set_max_write_buffer_number(config['max_write_buffer_number'])
        if 'min_write_buffer_number' in config:
            opts.set_min_write_buffer_number(config['min_write_buffer_number'])
        if 'level0_file_num_compaction_trigger' in config:
            opts.set_level_zero_file_num_compaction_trigger(config['level0_file_num_compaction_trigger'])
        if 'max_background_jobs' in config:
            opts.set_max_background_jobs(config['max_background_jobs'])
        if 'enable_pipelined_write' in config:
            opts.set_enable_pipelined_write(config['enable_pipelined_write'])
            
        # 创建 block-based 表选项
        block_opts = BlockBasedOptions()
        block_opts.set_block_cache(self._block_cache)
        block_opts.set_bloom_filter(int(get_env("ROCKSDB_BLOOM_BITS")), True)
        opts.set_block_based_table_factory(block_opts)
        
        return opts

    def make_key(self, pattern: KeyPattern, **kwargs) -> str:
        """构造键
        
        Args:
            pattern: 键模式
            **kwargs: 键组成部分
            
        Returns:
            构造的键
            
        Examples:
            >>> make_key(KeyPattern.PREFIX_ID, prefix="user", id="123")
            "user:123"
            >>> make_key(KeyPattern.PREFIX_INFIX_PATH_VALUE, 
                        prefix="index", infix="name", path="users", value="zhang")
            "index:name:users:zhang"
        """
        parts = []
        
        if pattern == KeyPattern.PREFIX_ID:
            parts = [kwargs['prefix'], kwargs['id']]
        elif pattern == KeyPattern.PREFIX_ID_SUFFIX:
            parts = [kwargs['prefix'], kwargs['id'], kwargs['suffix']]
        elif pattern == KeyPattern.PREFIX_INFIX_ID:
            parts = [kwargs['prefix'], kwargs['infix'], kwargs['id']]
        elif pattern == KeyPattern.PREFIX_INFIX_ID_SUFFIX:
            parts = [kwargs['prefix'], kwargs['infix'], kwargs['id'], kwargs['suffix']]
        elif pattern == KeyPattern.PREFIX_PATH_VALUE:
            parts = [kwargs['prefix'], kwargs['path'], kwargs['value']]
        elif pattern == KeyPattern.PREFIX_INFIX_PATH_VALUE:
            parts = [kwargs['prefix'], kwargs['infix'], kwargs['path'], kwargs['value']]
            
        return ":".join(str(p).strip(":") for p in parts if p)
        
    def validate_key(self, key: str) -> bool:
        """验证键是否合法"""
        if isinstance(key, bytes):
            key = key.decode()
            
        patterns = [
            r'^[^:]+:[^:]+$',  # prefix:id
            r'^[^:]+:[^:]+:[^:]+$',  # prefix:id:suffix
            r'^[^:]+:[^:]+:[^:]+$',  # prefix:infix:id
            r'^[^:]+:[^:]+:[^:]+:[^:]+$',  # prefix:infix:id:suffix
            r'^[^:]+:[^:]+:[^:]+$',  # prefix:path:value  
            r'^[^:]+:[^:]+:[^:]+:[^:]+$'  # prefix:infix:path:value
        ]
        return any(re.match(p, key) for p in patterns)
        
    def list_collections(self) -> List[str]:
        """列出所有集合（列族）"""
        return Rdict.list_cf(str(self._db_path))
        
    def set_collection_options(self, name: str, options: Dict[str, Any]) -> None:
        """设置集合（列族）配置"""
        if name not in self._collections:
            opts = self._create_options(options)
            self._collections[name] = self._db.create_column_family(name, opts)
            self._collection_configs[name] = options
        else:
            raise ValueError(f"集合 {name} 已存在")
            
    def get(self, collection: str, key: str) -> Optional[Any]:
        """获取值"""
        if not self.validate_key(key):
            raise ValueError(f"非法键格式: {key}")
            
        cf = self.get_collection(collection)
        value = cf.get(key.encode())
        return value  # 不需要手动反序列化，rocksdict 会使用我们设置的 msgpack.unpackb
        
    def set(self, collection: str, key: str, value: Any) -> None:
        """设置值"""
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
            if start:
                it.seek(start.encode())  # 转换为字节串
            else:
                it.seek_to_first()
                
            # 迭代所有键
            while it.valid():
                key_bytes = it.key()
                key = key_bytes.decode() if isinstance(key_bytes, bytes) else key_bytes
                
                # 检查是否超过结束位置
                if end and key > end:  # 使用字符串比较
                    break
                    
                if limit and count >= limit:
                    break
                    
                if prefix and not key.startswith(prefix):
                    break
                    
                if pattern and not self.validate_key(key):
                    it.next()
                    continue
                    
                yield key
                count += 1
                it.next()
                
        finally:
            del it
            
    def first(self, collection: str, pattern: Optional[KeyPattern] = None) -> Optional[Tuple[str, Any]]:
        """获取第一个键值对"""
        cf = self.get_collection(collection)
        it = cf.iter()
        
        try:
            it.seek_to_first()
            while it.valid():
                key = it.key()
                if isinstance(key, bytes):
                    key = key.decode()
                    
                if not pattern or self.validate_key(key):
                    value = it.value()  # 迭代器返回的值已经被 rocksdict 自动反序列化
                    return key, value
                it.next()
        finally:
            del it
        return None
        
    def last(self, collection: str, pattern: Optional[KeyPattern] = None) -> Optional[Tuple[str, Any]]:
        """获取最后一个键值对"""
        cf = self.get_collection(collection)
        it = cf.iter()
        
        try:
            it.seek_to_last()
            while it.valid():
                key = it.key()
                if isinstance(key, bytes):
                    key = key.decode()
                    
                if not pattern or self.validate_key(key):
                    value = it.value()  # 迭代器返回的值已经被 rocksdict 自动反序列化
                    return key, value
                it.prev()
        finally:
            del it
        return None
        
    def all(self, collection: str, pattern: Optional[KeyPattern] = None) -> List[Tuple[str, Any]]:
        """获取所有键值对"""
        return [(k, self.get(collection, k)) for k in self.iter_keys(collection, pattern=pattern)]
        
    def delete(self, collection: str, key: str) -> None:
        """删除键值对"""
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
        if hasattr(self, '_block_cache'):
            del self._block_cache
        if hasattr(self, '_row_cache'):
            del self._row_cache
        
    def get_statistics(self) -> Dict[str, Any]:
        """获取数据库基本信息"""
        stats = {}
        try:
            # 获取数据库文件大小
            db_path = Path(self._db_path)
            if db_path.exists():
                stats["disk_usage"] = sum(f.stat().st_size for f in db_path.rglob('*') if f.is_file())
            
            # 获取所有集合的大致键数量
            total_keys = 0
            for collection in self.list_collections():
                cf = self.get_collection(collection)
                # 使用 keys() 方法计数
                count = sum(1 for _ in cf.keys())
                total_keys += count
            
            stats["num_entries"] = total_keys
                
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
                opts = self._create_options(self._default_cf_options)
                self._collections[name] = self._db.create_column_family(name, opts)
        return self._collections[name]
