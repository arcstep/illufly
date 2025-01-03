from typing import Optional, Any, List, Dict, Set, Iterator, Tuple, Union, Type
from rocksdict import (
    Rdict, Options, ColumnFamily, ReadOptions,
    Cache, BlockBasedOptions, WriteBufferManager
)
import msgpack
from pathlib import Path
import re

from ...config import get_env
from .patterns import KeyPattern, RocksDBConfig
from .model import HuangIndexModel
from .registry import ModelRegistry

class RocksDB:
    """RocksDB存储后端"""
    
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
        
        # 修改序列化方法以支持 Pydantic 模型
        def dumps(obj: Any) -> bytes:
            if isinstance(obj, HuangIndexModel):
                return msgpack.packb({
                    "__model__": obj.__class__.__name__,
                    "__collection__": obj.__collection__,
                    "data": obj.model_dump()
                })
            return msgpack.packb(obj)
            
        def loads(data: bytes) -> Any:
            obj = msgpack.unpackb(data)
            if isinstance(obj, dict) and "__model__" in obj:
                model_class = ModelRegistry.get(obj["__model__"])
                return model_class(**obj["data"])
            return obj
            
        self._db.set_dumps(dumps)
        self._db.set_loads(loads)
        
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
        if hasattr(self, '_config'):
            del self._config
        
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
                opts = self._config.create_options(self._default_cf_options)
                self._collections[name] = self._db.create_column_family(name, opts)
        return self._collections[name]
