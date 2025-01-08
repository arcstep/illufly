from rocksdict import Rdict, Options, WriteBatch, SstFileWriter, ReadOptions, WriteOptions
from typing import Any, Iterator, Optional, Union, Tuple, Literal
import logging
import itertools
from dataclasses import dataclass
from enum import Enum

class BaseRocksDB:
    """RocksDB基础封装类
    
    提供核心的键值存储功能，支持：
    1. 基础的键值操作
    2. 可选的Rdict实例（批处理、列族等）
    3. 默认列族访问
    
    Examples:
        # 基础使用
        with BaseRocksDB("path/to/db") as db:
            db["key"] = value
            
        # 使用列族
        with BaseRocksDB("path/to/db") as db:
            default_cf = db.default_cf
            users_cf = db.get_column_family("users")
            
            # 写入不同列族
            db.put("key", value, default_cf)  # 等同于 db["key"] = value
            db.put("user:1", user_data, users_cf)
            
        # 批量写入
        with BaseRocksDB("path/to/db") as db:
            with db.batch_write() as batch:
                db.put("key1", value1, batch)
                db.put("key2", value2, batch)
    """

    def __init__(
        self,
        path: str,
        options: Optional[Options] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.path = path
        self._db = Rdict(path, options)
        self._logger = logger or logging.getLogger(__name__)
        self._default_cf = self._db.get_column_family("default")

    def not_exist(
        self,
        key: Any,
        *,
        rdict: Optional[Rdict] = None,
        options: Optional[ReadOptions] = None,
    ) -> bool:
        """快速检查键是否不存在（无 IO）
        
        Args:
            key: 要检查的键
            rdict: 可选的Rdict实例（如列族等）
            options: 读取选项
            
        Returns:
            True: 键确定不存在
            False: 键可能存在（需要进一步确认）
            
        Examples:
            if db.not_exist("user:123"):
                print("用户不存在")
                return
        """
        target = rdict if rdict is not None else self._db
        return not target.key_may_exist(key, False, options)

    def exist(
        self,
        key: Any,
        *,
        rdict: Optional[Rdict] = None,
        options: Optional[ReadOptions] = None,
    ) -> Tuple[bool, Optional[Any]]:
        """快速检查键是否存在（轻量级 IO）
        
        Args:
            key: 要检查的键
            rdict: 可选的Rdict实例（如列族等）
            options: 读取选项
            
        Returns:
            (exists, value):
                - (True, value): 键存在，返回对应的值
                - (False, None): 需要进一步确认
            
        Examples:
            exists, value = db.exist("user:123")
            if exists:
                print("用户存在:", value)
                return value
        """
        target = rdict if rdict is not None else self._db
        exists, value = target.key_may_exist(key, True, options)
        if exists and value is not None:
            return True, value
        return False, None 

    def put(
        self,
        key: Any,
        value: Any,
        *,
        rdict: Optional[Rdict] = None,
        options: Optional[WriteOptions] = None,
    ) -> None:
        """写入数据
        
        Args:
            key: 数据键
            value: 要写入的值
            rdict: 可选的Rdict实例（如批处理器、列族等）
            options: 写入选项
            
        Examples:
            # 基本写入
            db.put("key", "value")
            
            # 使用写入选项
            opts = WriteOptions()
            opts.disable_wal(True)  # 禁用预写日志以提高性能
            db.put("key", "value", options=opts)
            
            # 写入列族
            users_cf = db.get_column_family("users")
            db.put("user:1", user_data, rdict=users_cf)
        """
        target = rdict if rdict is not None else self._db
        target.put(key, value, options)

    def delete(self, key: Any, rdict: Optional[Rdict] = None) -> None:
        """删除数据
        
        Args:
            key: 要删除的键
            rdict: 可选的Rdict实例（如批处理器、列族等）
        """
        target = rdict if rdict is not None else self._db
        del target[key]

    def get(
        self,
        key: Union[Any, list[Any]],
        *,
        default: Any = None,
        rdict: Optional[Rdict] = None,
        options: Optional[ReadOptions] = None,
    ) -> Any:
        """获取数据
        
        Args:
            key: 单个键或键列表
            default: 键不存在时的默认返回值
            rdict: 可选的Rdict实例（如列族等）
            options: 读取选项
            
        Returns:
            存储的值，如果键不存在则返回默认值
        """
        target = rdict if rdict is not None else self._db
        try:
            return target.get(key, default, options)
        except KeyError:
            return default

    def iter(
        self,
        *,
        rdict: Optional[Rdict] = None,
        prefix: Optional[str] = None,
        start: Optional[Any] = None,
        end: Optional[Any] = None,
        reverse: bool = False,
        fill_cache: bool = True,
        options: Optional[ReadOptions] = None,
    ) -> Iterator[Tuple[Any, Any]]:
        """返回键值对迭代器
        
        Args:
            start: 起始键（包含）
            end: 结束键（不包含）
            reverse: 是否反向迭代
            
        Note:
            如果 start > end，会自动交换两者的值
        """
        # 如果 start 和 end 都存在，确保 start < end
        if start is not None and end is not None and start > end:
            start, end = end, start
            reverse = not reverse  # 同时翻转迭代方向
        
        target = rdict if rdict is not None else self._db
        
        self._logger.info(f"Starting iteration with parameters:")
        self._logger.info(f"- prefix: {prefix!r}")
        self._logger.info(f"- start: {start!r}")
        self._logger.info(f"- end: {end!r}")
        self._logger.info(f"- reverse: {reverse}")
        
        opts = options or ReadOptions()
        if not fill_cache:
            opts.fill_cache(False)
        
        it = target.iter(opts)
        self._logger.info("Iterator created")
        
        # 设置迭代器起始位置
        if reverse:
            if end is not None:  # 反向时从 end 开始
                self._logger.info(f"Reverse iteration: seeking to end: {end!r}")
                it.seek(end)
                if it.valid() and it.key() >= end:  # 如果找到了 end，需要往前移一位
                    it.prev()
            else:
                self._logger.info("Reverse iteration: seeking to last")
                it.seek_to_last()
        else:
            if start is not None:
                self._logger.info(f"Forward iteration: seeking to start: {start!r}")
                it.seek(start)
            elif prefix is not None:
                self._logger.info(f"Forward iteration: seeking to prefix: {prefix!r}")
                it.seek(prefix)
            else:
                self._logger.info("Forward iteration: seeking to first")
                it.seek_to_first()
        
        # 迭代并应用过滤
        count = 0
        while it.valid():
            key = it.key()
            self._logger.info(f"Checking key: {key!r}")
            
            # 检查前缀
            if prefix is not None and not key.startswith(prefix):
                self._logger.info(f"Key {key!r} doesn't match prefix {prefix!r}")
                break
            
            # 检查范围
            if reverse:
                if start is not None and key < start:  # 反向时 start 是下界（包含）
                    self._logger.info(f"Key {key!r} less than start {start!r}")
                    break
                if end is not None and key >= end:  # 反向时 end 是上界（不包含）
                    self._logger.info(f"Key {key!r} greater or equal to end {end!r}")
                    it.prev()
                    continue
            else:
                if start is not None and key < start:  # 正向时 start 是下界（包含）
                    self._logger.info(f"Key {key!r} less than start {start!r}")
                    break
                if end is not None and key >= end:  # 正向时 end 是上界（不包含）
                    self._logger.info(f"Key {key!r} greater or equal to end {end!r}")
                    break
            
            count += 1
            self._logger.info(f"Yielding key: {key!r} (count: {count})")
            yield key, it.value()
            
            if reverse:
                it.prev()
            else:
                it.next()
        
        self._logger.info(f"Iterator finished, yielded {count} items")

    def items(
        self,
        *,
        rdict: Optional[Rdict] = None,
        prefix: Optional[str] = None,
        start: Optional[Any] = None,
        end: Optional[Any] = None,
        reverse: bool = False,
        limit: Optional[int] = None,
        fill_cache: bool = True,
        options: Optional[ReadOptions] = None,
    ) -> list[Tuple[Any, Any]]:
        """返回键值对列表
        
        Args:
            options: 自定义读取选项
            rdict: 可选的Rdict实例（如列族等）
            prefix: 键前缀过滤
            start: 起始键（包含）
            end: 结束键（不包含）
            reverse: 是否反向迭代
            limit: 限制返回的项目数量
            fill_cache: 是否将扫描的数据填充到块缓存中
        """
        iterator = self.iter(
            rdict=rdict,
            prefix=prefix,
            start=start,
            end=end,
            reverse=reverse,
            fill_cache=fill_cache,
            options=options,
        )
        if limit is not None:
            return list(itertools.islice(iterator, limit))
        return list(iterator)
    
    def keys(self, *args, **kwargs) -> list[Any]:
        """返回键列表"""
        return [k for k, _ in self.items(*args, **kwargs)]
    
    def values(self, *args, **kwargs) -> list[Any]:
        """返回值列表"""
        return [v for _, v in self.items(*args, **kwargs)]
    
    def iter_keys(self, *args, **kwargs) -> Iterator[Any]:
        """返回键迭代器"""
        for k, _ in self.iter(*args, **kwargs):
            yield k
    
    def iter_values(self, *args, **kwargs) -> Iterator[Any]:
        """返回值迭代器"""
        for _, v in self.iter(*args, **kwargs):
            yield v
    
    def write(self, batch: WriteBatch) -> None:
        """执行批处理
        
        Args:
            batch: 要执行的批处理实例
            
        Examples:
            batch = db.batch()
            try:
                batch.put(key1, value1)
                batch.put(key2, value2)
                db.write(batch)
            except Exception as e:
                logger.error(f"Batch operation failed: {e}")
                raise
        """
        self._db.write(batch)
    
    def close(self) -> None:
        """关闭数据库"""
        self._db.close()
    
    @classmethod
    def destroy(cls, path: str, options: Optional[Options] = None) -> None:
        """删除数据库"""
        options = options or Options()
        Rdict.destroy(path, options) 

    @property
    def default_cf(self):
        """获取默认列族"""
        return self._default_cf
    
    def get_column_family(self, name: str):
        """获取指定名称的列族"""
        return self._db.get_column_family(name)

    @classmethod
    def list_column_families(cls, path: str, options: Optional[Options] = None) -> list[str]:
        """列举数据库中的所有列族
        
        Args:
            path: 数据库路径
            options: 可选的配置项
            
        Returns:
            列族名称列表
        """
        options = options or Options()
        return Rdict.list_cf(path, options)
    
    def create_column_family(self, name: str, options: Optional[Options] = None) -> Rdict:
        """创建新的列族
        
        Args:
            name: 列族名称
            options: 可选的列族配置
            
        Returns:
            新创建的列族实例
        """
        options = options or Options()
        return self._db.create_column_family(name, options)
    
    def drop_column_family(self, name: str) -> None:
        """删除指定的列族
        
        Args:
            name: 要删除的列族名称
        """
        self._db.drop_column_family(name)
    
    def get_column_family_handle(self, name: str):
        """获取列族句柄（用于批处理操作）
        
        Args:
            name: 列族名称
            
        Returns:
            列族句柄
            
        Examples:
            with db.batch_write() as batch:
                cf_handle = db.get_column_family_handle("users")
                batch.put(key, value, cf_handle)
        """
        return self._db.get_column_family_handle(name) 

    def __getitem__(self, key: Any) -> Any:
        return self.get(key)
    
    def __setitem__(self, key: Any, value: Any) -> None:
        self.put(key, value)
    
    def __delitem__(self, key: Any) -> None:
        self.delete(key)



