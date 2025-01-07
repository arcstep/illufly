from rocksdict import Rdict, Options, WriteBatch, SstFileWriter
from typing import Any, Iterator, Optional, Protocol
from abc import ABC, abstractmethod
import logging

class IndexManager(ABC):
    """索引管理的抽象接口"""
    
    @abstractmethod
    def update_indexes(self, key: Any, value: Any, old_value: Any = None) -> None:
        """更新索引
        
        Args:
            key: 数据键
            value: 新值（None表示删除）
            old_value: 旧值（用于清理旧索引）
        """
        pass
    
    @abstractmethod
    def define_index(self, name: str, field_path: str) -> None:
        """定义索引
        
        Args:
            name: 索引名称
            field_path: 字段路径
        """
        pass

class RocksDict:
    """RocksDict基础封装类
    
    提供基础的键值存储功能，索引更新需要手动执行。
    
    Examples:
        # 基础键值操作
        with RocksDict("path/to/db") as db:
            db["key"] = "value"
            
        # 带索引的批量操作
        with RocksDict("path/to/db", index_manager=index_mgr) as db:
            # 1. 先执行数据写入
            with db.batch_write() as batch:
                for key, value in items:
                    batch.put(key, value)
            
            # 2. 再手动更新索引
            for key, value in items:
                db.update_index(key, value)
    """
    
    def __init__(
        self,
        path: str,
        options: Optional[Options] = None,
        index_manager: Optional[IndexManager] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.path = path
        self._db = Rdict(path, options)
        self._logger = logger or logging.getLogger(__name__)
        self._index_manager = index_manager
    
    def update_index(self, key: Any, value: Any, old_value: Any = None) -> None:
        """手动更新索引
        
        Args:
            key: 数据键
            value: 新值（None表示删除）
            old_value: 旧值（用于清理旧索引）
        """
        if self._index_manager:
            self._index_manager.update_indexes(key, value, old_value)
    
    def __getitem__(self, key: Any) -> Any:
        return self._db[key]
    
    def __setitem__(self, key: Any, value: Any) -> None:
        """设置键值对（不会自动更新索引）"""
        self._db[key] = value
    
    def __delitem__(self, key: Any) -> None:
        """删除键值对（不会自动更新索引）"""
        del self._db[key]
    
    def items(self) -> Iterator[tuple[Any, Any]]:
        """返回数据库中所有键值对的迭代器"""
        return self._db.items()
    
    def batch_write(self) -> WriteBatch:
        """创建批量写入器"""
        return self._db.write_batch()
    
    def close(self) -> None:
        """关闭数据库"""
        self._db.close()
    
    @classmethod
    def destroy(cls, path: str) -> None:
        """删除数据库"""
        Rdict.destroy(path)
    
    def put_with_index(self, key: Any, value: Any, rdict: Optional[Rdict] = None) -> None:
        """写入数据并更新索引
        
        Args:
            key: 数据键
            value: 要写入的值
            rdict: 可选的Rdict实例，如果提供则使用该实例执行写入操作
                  可以是批处理器、SST写入器、列族等
            
        Examples:
            # 使用默认实例
            db.put_with_index("key", value)
            
            # 使用批处理
            with db.batch_write() as batch:
                db.put_with_index("key", value, batch)
                
            # 使用列族
            cf = db._db.get_column_family("cf_name")
            db.put_with_index("key", value, cf)
        """
        target = rdict if rdict is not None else self._db
        
        try:
            old_value = self[key]
        except KeyError:
            old_value = None
            
        target[key] = value
        self.update_index(key, value, old_value)
    
    def del_with_index(self, key: Any, rdict: Optional[Rdict] = None) -> None:
        """删除数据并更新索引
        
        Args:
            key: 要删除的数据键
            rdict: 可选的Rdict实例，如果提供则使用该实例执行删除操作
                  可以是批处理器、SST写入器、列族等
            
        Examples:
            # 使用默认实例
            db.del_with_index("key")
            
            # 使用批处理
            with db.batch_write() as batch:
                db.del_with_index("key", batch)
                
            # 使用列族
            cf = db._db.get_column_family("cf_name")
            db.del_with_index("key", cf)
        """
        target = rdict if rdict is not None else self._db
        old_value = self[key]
        del target[key]
        self.update_index(key, None, old_value)