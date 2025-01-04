from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union
from rocksdict import DBCompressionType, WriteBufferManager, Cache, Options, BlockBasedOptions
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
    
    @classmethod
    def validate_key(cls, key: str) -> bool:
        """验证键是否符合任一模式"""
        if isinstance(key, bytes):
            key = key.decode()
            
        patterns = [
            r'^[^:]+:[^:]+$',  # prefix:id
            r'^[^:]+:[^:]+:[^:]+$',  # prefix:id:suffix 或 prefix:infix:id
            r'^[^:]+:[^:]+:[^:]+:[^:]+$',  # prefix:infix:id:suffix 或 prefix:infix:path:value
        ]
        return any(re.match(p, key) for p in patterns)
        
    @classmethod
    def make_key(cls, pattern: 'KeyPattern', **kwargs) -> str:
        """构造键
        
        Args:
            pattern: 键模式
            **kwargs: 键组成部分
            
        Returns:
            构造的键
        """
        def sanitize(value: Any) -> str:
            """清理键值中的非法字符"""
            if value is None:
                return ''
            # 将冒号替换为下划线
            return str(value).replace(':', '_')
        
        parts = []
        
        if pattern == cls.PREFIX_ID:
            parts = [kwargs['prefix'], kwargs['id']]
        elif pattern == cls.PREFIX_ID_SUFFIX:
            parts = [kwargs['prefix'], kwargs['id'], kwargs['suffix']]
        elif pattern == cls.PREFIX_INFIX_ID:
            parts = [kwargs['prefix'], kwargs['infix'], kwargs['id']]
        elif pattern == cls.PREFIX_INFIX_ID_SUFFIX:
            parts = [kwargs['prefix'], kwargs['infix'], kwargs['id'], kwargs['suffix']]
        elif pattern == cls.PREFIX_PATH_VALUE:
            parts = [kwargs['prefix'], kwargs['path'], kwargs['value']]
        elif pattern == cls.PREFIX_INFIX_PATH_VALUE:
            parts = [kwargs['prefix'], kwargs['infix'], kwargs['path'], kwargs['value']]
            
        # 对每个部分进行清理
        parts = [sanitize(p) for p in parts]
        return ":".join(p for p in parts if p)

@dataclass
class RocksDBConfig:
    """RocksDB 配置"""
    collection_name: str
    
    def __post_init__(self):
        # 从环境变量加载配置
        self.write_buffer_size = int(get_env("ROCKSDB_WRITE_BUFFER_SIZE")) * 1024 * 1024
        self.block_cache_size = int(get_env("ROCKSDB_BLOCK_CACHE_SIZE")) * 1024 * 1024
        self.row_cache_size = int(get_env("ROCKSDB_ROW_CACHE_SIZE")) * 1024 * 1024
        self.max_write_buffer_number = int(get_env("ROCKSDB_MAX_WRITE_BUFFER_NUMBER"))
        self.min_write_buffer_number = int(get_env("ROCKSDB_MIN_WRITE_BUFFER_NUMBER"))
        self.level0_file_num_compaction_trigger = int(get_env("ROCKSDB_LEVEL0_FILE_NUM_COMPACTION_TRIGGER"))
        self.max_background_jobs = int(get_env("ROCKSDB_MAX_BACKGROUND_JOBS"))
        self.enable_pipelined_write = bool(get_env("ROCKSDB_ENABLE_PIPELINED_WRITE"))
        self.bloom_bits = int(get_env("ROCKSDB_BLOOM_BITS"))
        
        # 压缩类型映射
        self._compression_map = {
            'none': DBCompressionType.none(),
            'snappy': DBCompressionType.snappy(),
            'lz4': DBCompressionType.lz4(),
            'zstd': DBCompressionType.zstd(),
            'bz2': DBCompressionType.bz2(),
            'lz4hc': DBCompressionType.lz4hc(),
            'zlib': DBCompressionType.zlib()
        }
        self.compression_type = self._compression_map.get(
            get_env("ROCKSDB_DEFAULT_CF_COMPRESSION").lower(),
            DBCompressionType.lz4()
        )
        
        # 创建缓存实例
        self._block_cache = Cache(self.block_cache_size)
        self._row_cache = Cache(self.row_cache_size)
        
        # 创建写缓冲区管理器
        self._write_buffer_manager = WriteBufferManager.new_write_buffer_manager_with_cache(
            self.write_buffer_size, True, self._block_cache
        )
    
    @property
    def block_cache(self) -> Cache:
        """获取块缓存"""
        return self._block_cache
        
    @property
    def row_cache(self) -> Cache:
        """获取行缓存"""
        return self._row_cache
        
    @property
    def write_buffer_manager(self) -> WriteBufferManager:
        """获取写缓冲区管理器"""
        return self._write_buffer_manager
    
    def get_compression_type(self, compression: Optional[Union[str, DBCompressionType]] = None) -> DBCompressionType:
        """获取压缩类型
        
        Args:
            compression: 压缩类型，可以是字符串或 DBCompressionType 对象
            
        Returns:
            DBCompressionType 对象
        """
        if compression is None:
            return self.compression_type
            
        # 如果已经是 DBCompressionType 对象，直接返回
        if isinstance(compression, DBCompressionType):
            return compression
            
        # 如果是字符串，从映射中获取
        return self._compression_map.get(compression.lower(), DBCompressionType.lz4())
    
    @property
    def default_options(self) -> Dict[str, Any]:
        """获取默认列族选项"""
        return {
            'compression_type': self.compression_type,
            'write_buffer_size': self.write_buffer_size,
            'max_write_buffer_number': self.max_write_buffer_number,
            'min_write_buffer_number': self.min_write_buffer_number,
            'level0_file_num_compaction_trigger': self.level0_file_num_compaction_trigger,
            'max_background_jobs': self.max_background_jobs,
            'enable_pipelined_write': self.enable_pipelined_write
        }
        
    def create_options(self, config: Dict[str, Any]) -> Options:
        """创建Options对象"""
        opts = Options()
        opts.create_if_missing(True)
        
        # 基本选项设置
        if 'compression_type' in config:
            compression_type = self.get_compression_type(config['compression_type'])
            opts.set_compression_type(compression_type)
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
        block_opts.set_block_cache(self.block_cache)
        block_opts.set_bloom_filter(self.bloom_bits, True)
        opts.set_block_based_table_factory(block_opts)
        
        return opts 