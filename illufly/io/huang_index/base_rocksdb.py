from typing import Dict, Any, Optional, Iterator, List, Tuple, Set
from rocksdict import Rdict, WriteBatch, Options, ColumnFamily, ReadOptions
from pathlib import Path
from contextlib import contextmanager

import msgpack
import logging

from ...config import get_env
from .rocksdb_config import RocksDBConfig

# 配置日志
logging.basicConfig()

class BaseRocksDB:
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
    
    # 系统列族名称
    SYSTEM_CF = "__system__"
    # 默认列族名称
    DEFAULT_CF = "__default__"
    # 列族配置的键名
    CF_CONFIGS_KEY = "collection_configs"
    
    # 添加类级别的常量
    DEFAULT_BATCH_SIZE = 1000  # 默认批处理大小
    MAX_ITEMS_LIMIT = 10000   # 最大返回条数限制
    
    def __init__(
        self, db_path: Optional[str] = None, 
        system_options: Optional[Dict[str, Any]] = None,
        collections: Optional[Dict[str, Dict]] = None, 
        logger: Optional[logging.Logger] = None
    ):
        """初始化RocksDB
        
        Args:
            db_path: 数据库路径
            system_options: 系统列族的配置选项
            collections: 其他系统/元数据列族的配置字典
            logger: 日志记录器
        """
        self._logger = logger or logging.getLogger(__name__)
        self._db_path = Path(db_path or get_env("ROCKSDB_BASE_DIR"))
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # 使用 RocksDBConfig 创建默认配置
        self._config = RocksDBConfig(self.DEFAULT_CF)
        self._default_cf_options = self._config.default_options
        
        # 初始化所有系统/元数据列族配置
        self._meta_collections = {}
        
        # 1. 添加系统列族配置
        self._meta_collections[self.SYSTEM_CF] = system_options or {}
        
        # 2. 添加其他系统/元数据列族配置
        if collections:
            self._meta_collections.update(collections)
            
        self._collection_configs: Dict[str, Options] = {}
        self._collections: Dict[str, Rdict] = {}
        self._cf_handles: Dict[str, ColumnFamily] = {}
        
        # 打开数据库并初始化所有系统/元数据列族
        self._db = self._init_db_with_system()
        
        # 初始化其他已存在的列族（非系统/元数据列族）
        self._init_existing_collections()
        
        self._logger.info(f"Initialized BaseRocksDB with path: {db_path}")
        
    def _init_db_with_system(self) -> Rdict:
        """初始化数据库并确保元数据列族存在"""
        db = Rdict(str(self._db_path))
        
        try:
            existing_cfs = Rdict.list_cf(str(self._db_path))
            
            # 1. 确保系统列族存在并初始化
            if self.SYSTEM_CF not in existing_cfs:
                self._logger.info(f"Creating system column family: {self.SYSTEM_CF}")
                self._logger.info(f"System options: {self._meta_collections[self.SYSTEM_CF]}")
                opts = self._config.create_options(self._meta_collections[self.SYSTEM_CF])
                db.create_column_family(self.SYSTEM_CF, opts)
                system_cf = db.get_column_family(self.SYSTEM_CF)
                # 初始化配置存储，包括系统列族自身的配置
                stored_configs = {
                    self.SYSTEM_CF: self._meta_collections[self.SYSTEM_CF]
                }
                self._logger.info(f"Saving initial configs: {stored_configs}")
                system_cf[self.CF_CONFIGS_KEY] = stored_configs
                
            # 初始化系统列族的句柄和配置
            self._collections[self.SYSTEM_CF] = db.get_column_family(self.SYSTEM_CF)
            self._cf_handles[self.SYSTEM_CF] = db.get_column_family_handle(self.SYSTEM_CF)
            self._collection_configs[self.SYSTEM_CF] = self._meta_collections[self.SYSTEM_CF]
            
            # 2. 初始化其他元数据列族
            for cf_name, options in self._meta_collections.items():
                if cf_name == self.SYSTEM_CF:
                    continue
                    
                if cf_name not in existing_cfs:
                    self._logger.info(f"Creating metadata column family: {cf_name}")
                    self._logger.info(f"Options: {options}")
                    opts = self._config.create_options(options)
                    self._collections[cf_name] = db.create_column_family(cf_name, opts)
                    self._cf_handles[cf_name] = db.get_column_family_handle(cf_name)
                    self._collection_configs[cf_name] = options
                    
                    # 更新系统列族中的配置
                    system_cf = self._collections[self.SYSTEM_CF]
                    stored_configs = system_cf.get(self.CF_CONFIGS_KEY, {})
                    stored_configs[cf_name] = options
                    self._logger.info(f"Updating stored configs: {stored_configs}")
                    system_cf[self.CF_CONFIGS_KEY] = stored_configs
                else:
                    self._collections[cf_name] = db.get_column_family(cf_name)
                    self._cf_handles[cf_name] = db.get_column_family_handle(cf_name)
                    self._collection_configs[cf_name] = options
                    
            # 3. 确保所有元数据列族的配置都被保存
            system_cf = self._collections[self.SYSTEM_CF]
            stored_configs = system_cf.get(self.CF_CONFIGS_KEY, {})
            
            # 只更新非空的配置
            for cf_name, options in self._meta_collections.items():
                if options:  # 只有当配置不为空时才更新
                    stored_configs[cf_name] = options
            
            self._logger.info(f"Final stored configs: {stored_configs}")
            system_cf[self.CF_CONFIGS_KEY] = stored_configs
            
        except Exception as e:
            if "already exists" not in str(e):
                raise ValueError(f"初始化元数据列族失败: {str(e)}") from e
                
        return db
        
    def _init_existing_collections(self):
        """初始化已存在的列族"""
        try:
            existing_cfs = Rdict.list_cf(str(self._db_path))
            self._logger.info(f"Found existing collections: {existing_cfs}")
            
            # 加载持久化的配置
            system_cf = self._db.get_column_family(self.SYSTEM_CF)
            stored_configs = system_cf.get(self.CF_CONFIGS_KEY, {})
            self._logger.info(f"Loaded stored configs: {stored_configs}")
            
            # 初始化所有列族
            for cf_name in existing_cfs:
                self._collections[cf_name] = self._db.get_column_family(cf_name)
                self._cf_handles[cf_name] = self._db.get_column_family_handle(cf_name)
                
                # 获取持久化的配置
                stored_config = stored_configs.get(cf_name)
                if stored_config:
                    self._logger.info(f"Using stored config for {cf_name}: {stored_config}")
                    self._collection_configs[cf_name] = stored_config
                    
                    # 如果是元数据列族，检查入参配置
                    if cf_name in self._meta_collections:
                        input_config = self._meta_collections[cf_name]
                        if input_config:  # 只有当入参不为空时才进行校验
                            self._logger.info(f"Validating input config for {cf_name}: {input_config}")
                            for key, value in input_config.items():
                                if key in stored_config and stored_config[key] != value:
                                    raise ValueError(
                                        f"列族 '{cf_name}' 的配置与预期不符: "
                                        f"存储值 {stored_config[key]} != 预期值 {value} "
                                        f"(键: {key})"
                                    )
                else:
                    # 对于普通列族，使用默认配置
                    self._logger.info(f"Using default config for {cf_name}")
                    self._collection_configs[cf_name] = self._default_cf_options.copy()
                
                self._logger.info(f"Initialized existing collection: {cf_name}")
                
        except Exception as e:
            self._logger.error(f"Error initializing existing collections: {e}", exc_info=True)
            raise ValueError(f"初始化已存在的列族失败: {str(e)}") from e

    def set_collection_options(self, name: str, options: Dict[str, Any]) -> None:
        """设置集合（列族）配置"""
        if name == self.SYSTEM_CF:
            raise ValueError(f"不能修改系统列族: {self.SYSTEM_CF}")
            
        # 检查列族是否已存在
        existing_cfs = Rdict.list_cf(str(self._db_path))
        if name in existing_cfs:
            raise ValueError(f"集合 '{name}' 已存在")
            
        try:
            # 创建新的列族
            opts = self._config.create_options(options)
            self._collections[name] = self._db.create_column_family(name, opts)
            self._cf_handles[name] = self._db.get_column_family_handle(name)
            self._collection_configs[name] = options
            
            # 更新存储的配置
            system_cf = self._db.get_column_family(self.SYSTEM_CF)
            stored_configs = system_cf.get(self.CF_CONFIGS_KEY, {})
            stored_configs[name] = options
            system_cf[self.CF_CONFIGS_KEY] = stored_configs
            
            self._logger.info(f"Created new collection with options: {name}")
            
        except Exception as e:
            # 清理可能的部分状态
            if name in self._collections:
                del self._collections[name]
            if name in self._cf_handles:
                del self._cf_handles[name]
            if name in self._collection_configs:
                del self._collection_configs[name]
            raise ValueError(f"创建集合 '{name}' 失败: {str(e)}") from e
            
    def get_collection_options(self, name: str) -> Dict[str, Any]:
        """获取集合配置
        
        Args:
            name: 集合名称
            
        Returns:
            Dict[str, Any]: 集合的配置选项
            
        Raises:
            ValueError: 如果集合不存在
        """
        # 优先使用 _collection_configs 中的配置（这里存储了从持久化读取的配置）
        if name in self._collection_configs:
            return self._collection_configs[name].copy()
        
        raise ValueError(f"集合 '{name}' 不存在")
        
    def list_collections(self) -> List[str]:
        """列出所有集合（列族）"""
        return Rdict.list_cf(str(self._db_path))
        
    def get(self, collection: str, key: str) -> Optional[Any]:
        """获取值
        
        Args:
            collection: 集合名称
            key: 键名
            
        Returns:
            Optional[Any]: 键对应的值,如果不存在则返回None
            
        """
        cf = self.get_collection(collection)
        value = cf.get(key.encode())
        return value  # 不需要手动反序列化，rocksdict 会使用我们设置的 msgpack.unpackb
        
    def set(self, collection: str, key: str, value: Any) -> None:
        """设置值
        
        Args:
            collection: 集合名称
            key: 键名
            value: 要存储的值            
        """            
        cf = self.get_collection(collection)
        cf[key.encode()] = value  # 不需要手动序列化，rocksdict 会使用我们设置的 msgpack.packb
        
    def iter_keys(self,
                collection: str,
                prefix: Optional[str] = None,
                start: Optional[str] = None,
                end: Optional[str] = None,
                limit: Optional[int] = None,
                reverse: bool = False,
                range_type: str = "[]") -> Iterator[str]:
        """迭代键
        
        Args:
            collection: 集合名称
            prefix: 前缀匹配
            start: 范围开始
            end: 范围结束
            limit: 限制数量
            reverse: 是否反向迭代
            range_type: 区间类型，支持:
                - "[]": 闭区间 [start, end]（默认）
                - "[)": 左闭右开区间 [start, end)
                - "(]": 左开右闭区间 (start, end]
                - "()": 开区间 (start, end)
        
        Raises:
            ValueError: 当 range_type 不是有效的区间类型时
        """
        if range_type not in ("[]", "[)", "(]", "()"):
            raise ValueError("无效的区间类型，必须是 [], [), (], () 之一")
        
        include_start = range_type[0] == "["
        include_end = range_type[1] == "]"
        
        cf = self.get_collection(collection)
        read_opts = ReadOptions()
        
        # 获取迭代器
        it = cf.iter(read_opts)
        count = 0
        
        try:
            # 设置起始位置
            if reverse:
                if prefix:
                    it.seek_for_prev((prefix + '\xff').encode())
                elif end:
                    it.seek_for_prev(end.encode())
                else:
                    it.seek_to_last()
            else:
                if prefix:
                    it.seek(prefix.encode())
                elif start:
                    # 对于左开区间，需要找到比start大的第一个键
                    if not include_start and start:
                        it.seek_for_prev(start.encode())
                        it.next()
                    else:
                        it.seek(start.encode())
                else:
                    it.seek_to_first()
            
            # 迭代所有键
            while it.valid():
                key_bytes = it.key()
                key = key_bytes.decode() if isinstance(key_bytes, bytes) else key_bytes
                
                # 检查前缀匹配
                if prefix:
                    if not key.startswith(prefix):
                        break
                
                # 检查范围
                if not reverse:
                    if start and not include_start and key <= start:
                        it.next()
                        continue
                    
                    if end:
                        if include_end:
                            if key > end:
                                break
                        else:
                            if key >= end:
                                break
                else:
                    if end and not include_end and key >= end:
                        it.prev()
                        continue
                    
                    if start:
                        if include_start:
                            if key < start:
                                break
                        else:
                            if key <= start:
                                break
                
                # 检查限制
                if limit and count >= limit:
                    break
                
                yield key
                count += 1
                it.next() if not reverse else it.prev()
                
        finally:
            del it
            
    def all(self, collection: str, limit: Optional[int] = DEFAULT_BATCH_SIZE) -> List[Tuple[str, Any]]:
        """获取集合中的所有数据
        
        Args:
            collection: 集合名称
            limit: 最大返回条数，None 表示不限制（但不建议），默认 1000 条
            
        Returns:
            List[Tuple[str, Any]]: 键值对列表
            
        Raises:
            ValueError: 如果 limit 超过了最大限制
        """
        if limit is not None and limit > self.MAX_ITEMS_LIMIT:
            raise ValueError(f"返回条数限制不能超过 {self.MAX_ITEMS_LIMIT}")
            
        self._logger.info(f"获取集合 {collection} 的所有数据，限制: {limit}")
        return [(key, self.get(collection, key)) 
                for key in self.iter_keys(collection, limit=limit)]
        
    def first(self, collection: str, prefix: Optional[str] = None,
            limit: Optional[int] = 1, range_type: str = "[]") -> Optional[Tuple[str, Any]]:
        """获取第一个键值对"""

        for key in self.iter_keys(
            collection=collection,
            prefix=prefix,
            limit=limit,
            range_type=range_type
        ):
            return key, self.get(collection, key)
        return None
        
    def last(self, collection: str, prefix: Optional[str] = None,
            limit: Optional[int] = 1, range_type: str = "[]") -> Optional[Tuple[str, Any]]:
        """获取最后一个键值对"""

        for key in self.iter_keys(
            collection=collection,
            prefix=prefix,
            reverse=True,
            limit=limit,
            range_type=range_type
        ):
            return key, self.get(collection, key)
        return None
        
    def delete(self, collection: str, key: str) -> None:
        """删除键值对
        
        Args:
            collection: 集合名称
            key: 要删除的键            
        """            
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
        if hasattr(self, '_db') and self._db is not None:
            # 清理所有列族的引用
            self._collections.clear()
            self._cf_handles.clear()
            self._collection_configs.clear()
            
            # 关闭数据库
            self._db.close()
            self._db = None
            
            # 等待锁释放（可选）
            import time
            time.sleep(0.1)  # 给系统一些时间来释放锁
        
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
                cf_config = self._collection_configs.get(collection, {})
                if not cf_config:  # 如果没有特定配置，使用默认配置
                    cf_config = self._default_cf_options
                
                # 记录列族统计，只包含实际设置的选项
                collection_options = {}
                for key in ['write_buffer_size', 'max_write_buffer_number', 
                           'min_write_buffer_number', 'level0_file_num_compaction_trigger']:
                    if key in cf_config:
                        collection_options[key] = cf_config[key]
                
                # 特殊处理 compression_type
                if 'compression_type' in cf_config:
                    collection_options['compression_type'] = str(cf_config['compression_type'])
                
                stats["collections"][collection] = {
                    "num_entries": count,
                    "options": collection_options
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
            self._logger.error(f"Error getting statistics: {e}", exc_info=True)
            
        return stats

    def get_collection(self, collection: str) -> Rdict:
        """获取集合的 Rdict 接口"""
        if collection not in self._collections:
            try:
                self._collections[collection] = self._db.get_column_family(collection)
            except Exception as e:
                raise ValueError(
                    f"集合 '{collection}' 不存在。请先使用 set_collection_options 创建该集合。"
                    f"\n当前可用的集合: {sorted(Rdict.list_cf(str(self._db_path)))}"
                ) from e
        return self._collections[collection]
        
    def get_cf_handle(self, collection: str) -> ColumnFamily:
        """获取集合的 ColumnFamily 句柄"""
        if collection not in self._cf_handles:
            try:
                self._cf_handles[collection] = self._db.get_column_family_handle(collection)
            except Exception as e:
                raise ValueError(
                    f"集合 '{collection}' 不存在。请先使用 set_collection_options 创建该集合。"
                    f"\n当前可用的集合: {sorted(Rdict.list_cf(str(self._db_path)))}"
                ) from e
        return self._cf_handles[collection]
        
    @contextmanager
    def batch_write(self) -> Iterator[None]:
        """批量写入上下文管理器"""
        batch = WriteBatch()
        self._logger.info("创建新的 WriteBatch")
        
        try:
            # 存储原始的 set/delete 方法
            original_set = self.set
            original_delete = self.delete
            
            # 重写 set/delete 方法以使用 batch
            def batch_set(collection: str, key: str, value: Any) -> None:
                cf = self._cf_handles[collection]
                # 通过闭包捕获外部的 batch 变量
                nonlocal batch
                batch.put(key.encode(), value, column_family=cf)
                if batch.len() % 50 == 0:
                    self._logger.info(f"批量写入: collection={collection}, key={key}, batch_size={batch.len()}")
            
            def batch_delete(collection: str, key: str) -> None:
                cf = self._cf_handles[collection]
                # 通过闭包捕获外部的 batch 变量
                nonlocal batch
                batch.delete(key.encode(), column_family=cf)
                self._logger.info(f"批量删除: collection={collection}, key={key}, batch_size={batch.len()}")
            
            # 替换方法
            self.set = batch_set
            self.delete = batch_delete
            self._logger.info("已替换原始的 set/delete 方法")
            
            yield batch  # 将 batch 对象传递给上下文
            
            # 如果没有异常，提交 batch
            self._logger.info(f"准备提交 batch，大小: {batch.len()}, 字节数: {batch.size_in_bytes()}")
            self._db.write(batch)
            self._logger.info("batch 提交完成")
            
        except Exception as e:
            self._logger.error(f"批量写入失败: {str(e)}", exc_info=True)
            raise
            
        finally:
            # 恢复原始方法
            self.set = original_set
            self.delete = original_delete
            self._logger.info("已恢复原始的 set/delete 方法")